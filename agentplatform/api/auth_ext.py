"""认证扩展 API(M24/需求 013/设计 018):GitHub OAuth / PAT / 邀请码 / 限频接线。"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.dependencies import get_current_user, require_admin
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.auth.oauth_model import (
    InviteCode,
    PersonalAccessToken,
    UserIdentity,
)
from agentplatform.core.auth.ratelimit import (
    account_locked,
    allow_ip_auth,
    allow_ip_register,
    clear_login_fail,
    record_login_fail,
)
from agentplatform.core.auth.service import (
    AuthError,
    authenticate,
    create_access_token,
    create_user,
    get_user_by_email,
)
from agentplatform.core.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


# ── GitHub OAuth ──────────────────────────────────────────────

GH_AUTHORIZE = "https://github.com/login/oauth/authorize"
GH_TOKEN = "https://github.com/login/oauth/access_token"
GH_USER = "https://api.github.com/user"
GH_EMAILS = "https://api.github.com/user/emails"


@router.get("/github")
async def github_login() -> RedirectResponse:
    """跳转 GitHub 授权(回调自动建号/绑定,同邮箱即绑定)。"""
    if not (settings.github_client_id and settings.github_client_secret):
        raise HTTPException(
            status_code=503,
            detail={"code": "not_configured", "message": "GitHub 登录未配置(缺 GITHUB_CLIENT_ID/SECRET)"},
        )
    redirect = f"{(settings.public_api_base or '').rstrip('/')}/api/auth/github/callback"
    url = (
        f"{GH_AUTHORIZE}?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect}&scope=read:user user:email"
    )
    return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(code: str, session: AsyncSession = Depends(get_session)) -> RedirectResponse:
    """换 token → 取身份与 primary 邮箱 → 绑定或建号 → 签发 JWT 回前端。"""
    if not (settings.github_client_id and settings.github_client_secret):
        raise HTTPException(status_code=503, detail={"code": "not_configured", "message": "GitHub 登录未配置"})
    redirect = f"{(settings.public_api_base or '').rstrip('/')}/api/auth/github/callback"
    async with httpx.AsyncClient(timeout=20) as hc:
        tok_resp = await hc.post(
            GH_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": redirect,
            },
        )
        access_token = (tok_resp.json() or {}).get("access_token")
        if not access_token:
            return RedirectResponse("/auth?error=github_denied")
        headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
        profile = (await hc.get(GH_USER, headers=headers)).json()
        emails = (await hc.get(GH_EMAILS, headers=headers)).json()

    uid = str(profile.get("id") or "")
    if not uid:
        return RedirectResponse("/auth?error=github_profile")
    email = next(
        (e.get("email") for e in emails if isinstance(e, dict) and e.get("primary")),
        None,
    ) or profile.get("email")

    # 已绑定 → 直接登录
    identity = await session.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == "github", UserIdentity.provider_uid == uid
        )
    )
    if identity is not None:
        user = await session.get(User, identity.user_id)
    else:
        user = await (get_user_by_email(session, email) if email else None) or _aio_none()
        if user is not None:
            session.add(UserIdentity(user_id=user.id, provider="github", provider_uid=uid))
        elif email:
            user = await create_user(session, email, secrets.token_urlsafe(24), UserRole.user)
            session.add(UserIdentity(user_id=user.id, provider="github", provider_uid=uid))
        else:
            return RedirectResponse("/auth?error=github_no_email")
    await session.commit()
    if user.disabled_at is not None:
        return RedirectResponse("/auth?error=disabled")
    token = create_access_token(str(user.id), user.role.value)
    return RedirectResponse(f"/auth?token={token}&github=1")


async def _aio_none():
    return None


# ── PAT ───────────────────────────────────────────────────────


class PatIn(BaseModel):
    name: str


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def verify_pat(raw: str) -> tuple[str, str] | None:
    """(仅供依赖层异步查库前的形态校验) ap_ 前缀 40 位。"""
    if raw.startswith("ap_") and len(raw) == 43:
        return raw, _hash_token(raw)
    return None


@router.get("/pat")
async def list_pats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        await session.scalars(
            select(PersonalAccessToken)
            .where(
                PersonalAccessToken.user_id == user.id,
                PersonalAccessToken.revoked_at.is_(None),
            )
            .order_by(PersonalAccessToken.created_at.desc())
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "prefix": r.prefix,
            "created_at": r.created_at.isoformat(),
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        }
        for r in rows
    ]


@router.post("/pat", status_code=201)
async def create_pat(
    payload: PatIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """生成 CLI 开发令牌:明文仅本次响应展示。"""
    raw = f"ap_{secrets.token_urlsafe(30)}"
    row = PersonalAccessToken(
        user_id=user.id,
        name=payload.name.strip()[:40] or "cli",
        token_hash=_hash_token(raw),
        prefix=raw[:8],
    )
    session.add(row)
    await session.commit()
    return {"id": str(row.id), "name": row.name, "token": raw}


@router.delete("/pat/{pat_id}")
async def revoke_pat(
    pat_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    row = await session.get(PersonalAccessToken, pat_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "令牌不存在"})
    row.revoked_at = datetime.now(UTC)
    await session.commit()
    return {"ok": True}


# ── 邀请码(admin)────────────────────────────────────────────


class InviteIn(BaseModel):
    count: int = 1
    max_uses: int = 1
    days_valid: int = 7


@router.get("/invites")
async def list_invites(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> list[dict]:
    rows = (
        await session.scalars(select(InviteCode).order_by(InviteCode.created_at.desc()).limit(100))
    ).all()
    return [
        {
            "id": str(r.id),
            "code": r.code,
            "max_uses": r.max_uses,
            "used_count": r.used_count,
            "disabled": r.disabled,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in rows
    ]


@router.post("/invites", status_code=201)
async def create_invites(
    payload: InviteIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> list[str]:
    """批量生成邀请码(一次性,默认 7 天有效)。"""
    codes = []
    expires = datetime.now(UTC) + timedelta(days=payload.days_valid)
    for _ in range(max(1, min(payload.count, 50))):
        code = f"inv-{secrets.token_hex(5)}"
        session.add(
            InviteCode(
                code=code,
                max_uses=max(1, payload.max_uses),
                expires_at=expires,
                created_by=str(user.id),
            )
        )
        codes.append(code)
    await session.commit()
    return codes


@router.delete("/invites/{code}")
async def disable_invite(
    code: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> dict:
    row = await session.scalar(select(InviteCode).where(InviteCode.code == code))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "邀请码不存在"})
    row.disabled = True
    await session.commit()
    return {"ok": True}


async def consume_invite(session: AsyncSession, code: str) -> None:
    """注册核销:无效/过期/用尽/作废抛 AuthError(403 语义)。"""
    row = await session.scalar(select(InviteCode).where(InviteCode.code == code.strip()))
    now = datetime.now(UTC)
    if (
        row is None
        or row.disabled
        or row.used_count >= row.max_uses
        or (row.expires_at is not None and row.expires_at < now)
    ):
        raise AuthError("invite_invalid", "邀请码无效或已使用", 403)
    row.used_count += 1


__all__ = [
    "router",
    "consume_invite",
    "allow_ip_auth",
    "allow_ip_register",
    "account_locked",
    "record_login_fail",
    "clear_login_fail",
    "_client_ip",
    "verify_pat",
    "_hash_token",
]
