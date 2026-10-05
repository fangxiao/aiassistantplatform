"""认证扩展 API(M24/需求 013/设计 018):GitHub/飞书 OAuth / PAT / 邀请码 / 限频接线。

M24 P2:OAuth 建号逻辑公共化(oauth_upsert_user)+ state 校验 + 双令牌签发
(设计 018 §7-§8)。
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.api.auth_session import issue_session
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
    create_user,
    get_user_by_email,
)
from agentplatform.core.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "oauth_state"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


# ── OAuth 公共:state + 建号/绑定(设计 018 §7-§8)──────────


def new_oauth_state() -> str:
    """生成一次性 state(回调与 cookie 比对防授权劫持)。"""
    return secrets.token_urlsafe(24)


def set_oauth_state_cookie(response: Response, state: str) -> None:
    """state 写短 cookie(5min,httpOnly);须挂在最终返回的响应上。"""
    response.set_cookie(
        STATE_COOKIE, state, max_age=300, path="/api/auth",
        httponly=True, samesite="lax",
        secure=(settings.public_api_base or "").startswith("https://"),
    )


def check_oauth_state(request: Request, state: str) -> bool:
    """回调 state 与 cookie 常量时间比对(编码后比较,容忍任意 cookie 内容)。"""
    import hmac as _hmac

    return bool(state) and _hmac.compare_digest(
        state.encode(), request.cookies.get(STATE_COOKIE, "").encode()
    )


async def oauth_upsert_user(
    session: AsyncSession,
    provider: str,
    uid: str,
    email: str,
    email_verified: bool = True,
) -> User | None:
    """身份落库(GitHub/飞书共用):已绑定直取 → 同邮箱绑定 → 免邀请码建号。

    email 必填(飞书无邮箱场景由调用方先合成占位邮箱);返回 None 仅当邮箱
    已被他人占用等异常——调用方以 error 回调兜底。
    """
    identity = await session.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider, UserIdentity.provider_uid == uid
        )
    )
    if identity is not None:
        return await session.get(User, identity.user_id)
    user = await get_user_by_email(session, email.lower())
    if user is None:
        user = await create_user(session, email, secrets.token_urlsafe(24), UserRole.user)
        if email_verified:
            user.email_verified_at = datetime.now(UTC)
    session.add(UserIdentity(user_id=user.id, provider=provider, provider_uid=uid))
    await session.commit()
    return user


async def _oauth_success_redirect(
    session: AsyncSession, user: User, request: Request, tag: str
) -> RedirectResponse:
    """双令牌签发到 redirect 响应(cookie)后回前端(token 参数落地)。"""
    resp = RedirectResponse("/auth")
    out = await issue_session(session, user, request, resp)
    resp.headers["location"] = f"/auth?token={out.token}&{tag}=1"
    return resp


# ── GitHub OAuth ──────────────────────────────────────────────

GH_AUTHORIZE = "https://github.com/login/oauth/authorize"
GH_TOKEN = "https://github.com/login/oauth/access_token"
GH_USER = "https://api.github.com/user"
GH_EMAILS = "https://api.github.com/user/emails"


@router.get("/github")
async def github_login() -> Response:
    """跳转 GitHub 授权(回调自动建号/绑定,同邮箱即绑定)。"""
    if not (settings.github_client_id and settings.github_client_secret):
        raise HTTPException(
            status_code=503,
            detail={"code": "not_configured", "message": "GitHub 登录未配置(缺 GITHUB_CLIENT_ID/SECRET)"},
        )
    redirect = f"{(settings.public_api_base or '').rstrip('/')}/api/auth/github/callback"
    state = new_oauth_state()
    resp = RedirectResponse(
        f"{GH_AUTHORIZE}?client_id={settings.github_client_id}"
        f"&redirect_uri={redirect}&scope=read:user user:email&state={state}"
    )
    # cookie 挂在最终返回的响应上(注入 response 参数对自定义响应不生效)
    set_oauth_state_cookie(resp, state)
    return resp


@router.get("/github/callback")
async def github_callback(
    request: Request,
    code: str,
    state: str = "",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """换 token → 取身份与 primary 邮箱 → 绑定或建号 → 双令牌回前端。"""
    if not (settings.github_client_id and settings.github_client_secret):
        raise HTTPException(status_code=503, detail={"code": "not_configured", "message": "GitHub 登录未配置"})
    if not check_oauth_state(request, state):
        return RedirectResponse("/auth?error=oauth_state")
    redirect_uri = f"{(settings.public_api_base or '').rstrip('/')}/api/auth/github/callback"
    async with httpx.AsyncClient(timeout=20) as hc:
        tok_resp = await hc.post(
            GH_TOKEN,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
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
    if not email:
        return RedirectResponse("/auth?error=github_no_email")

    user = await oauth_upsert_user(session, "github", uid, email, email_verified=True)
    if user is None or user.disabled_at is not None:
        return RedirectResponse("/auth?error=disabled")
    return await _oauth_success_redirect(session, user, request, "github")


# ── 飞书扫码登录(M24 P2/设计 018 §7)────────────────────────

FS_AUTHORIZE = "https://passport.feishu.cn/suite/passport/oauth/2.0/authorize"
FS_TOKEN = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FS_USERINFO = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def _feishu_configured() -> bool:
    return bool(settings.feishu_app_id and settings.feishu_app_secret)


@router.get("/feishu")
async def feishu_login() -> Response:
    """跳转飞书扫码授权页(passport)。"""
    if not _feishu_configured():
        raise HTTPException(
            status_code=503,
            detail={"code": "not_configured", "message": "飞书登录未配置(缺 FEISHU_APP_ID/SECRET)"},
        )
    redirect = f"{(settings.public_api_base or '').rstrip('/')}/api/auth/feishu/callback"
    state = new_oauth_state()
    resp = RedirectResponse(
        f"{FS_AUTHORIZE}?client_id={settings.feishu_app_id}"
        f"&redirect_uri={redirect}&response_type=code&state={state}"
    )
    set_oauth_state_cookie(resp, state)
    return resp


@router.get("/feishu/callback")
async def feishu_callback(
    request: Request,
    code: str,
    state: str = "",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """code 换 user_access_token → user_info → 绑定/建号 → 双令牌回前端。"""
    if not _feishu_configured():
        raise HTTPException(status_code=503, detail={"code": "not_configured", "message": "飞书登录未配置"})
    if not check_oauth_state(request, state):
        return RedirectResponse("/auth?error=oauth_state")
    redirect_uri = f"{(settings.public_api_base or '').rstrip('/')}/api/auth/feishu/callback"
    async with httpx.AsyncClient(timeout=20) as hc:
        tok_resp = await hc.post(
            FS_TOKEN,
            json={
                "grant_type": "authorization_code",
                "client_id": settings.feishu_app_id,
                "client_secret": settings.feishu_app_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        # v2 token 端点响应为顶层字段(不包 data);失败时 access_token 缺失
        tok = tok_resp.json() or {}
        user_access_token = tok.get("access_token")
        if not user_access_token:
            return RedirectResponse("/auth?error=feishu_denied")
        info = (
            await hc.get(FS_USERINFO, headers={"Authorization": f"Bearer {user_access_token}"})
        ).json()
    info = (info or {}).get("data") or {}
    uid = info.get("union_id") or info.get("open_id") or ""
    if not uid:
        return RedirectResponse("/auth?error=feishu_profile")
    email = info.get("email") or info.get("enterprise_email") or ""
    if not email:
        # 飞书侧邮箱不可见:合成内部域占位邮箱(不投递,不标记已验证;设计 018 §7)
        email = f"fs-{uid[:16]}@feishu.local"
        verified = False
    else:
        verified = True
    user = await oauth_upsert_user(session, "feishu", uid, email, email_verified=verified)
    if user is None or user.disabled_at is not None:
        return RedirectResponse("/auth?error=disabled")
    return await _oauth_success_redirect(session, user, request, "feishu")


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
    "_client_ip",
    "_hash_token",
    "account_locked",
    "allow_ip_auth",
    "allow_ip_register",
    "clear_login_fail",
    "consume_invite",
    "record_login_fail",
    "router",
    "verify_pat",
]
