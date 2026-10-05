"""双令牌会话层(M24 P2/需求 013 B1/设计 018 §6)。

- access:JWT HS256,2h,claim 增 typ="access";旧令牌(无 typ)按 legacy
  接受至自然过期——存量 30d JWT 兼容(延续 P1 A6)。
- refresh:不透明随机串 rf_<43>,sha256 落库可撤销;一次登录 = 一条
  family 轮换链,重放已轮换令牌 → 吊销全族(会话劫持信号)。
- refresh 仅经 httpOnly Cookie 流转,明文不落库不回传。

邮箱验证令牌(§9)同在本模块:JWT typ="email_verify",24h,不落库。
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.model import User
from agentplatform.core.auth.oauth_model import RefreshToken

ACCESS_TTL = timedelta(hours=2)
REFRESH_TTL = timedelta(days=30)
VERIFY_EMAIL_TTL = timedelta(hours=24)
REFRESH_PREFIX = "rf_"


# ── access ────────────────────────────────────────────────────

def create_access_token(subject: str, role: str) -> str:
    """签发 access JWT(HS256,2h,typ=access)。"""
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": subject, "role": role, "typ": "access", "iat": now, "exp": now + ACCESS_TTL},
        settings.secret_key,
        algorithm="HS256",
    )


def create_legacy_access_token(subject: str, role: str) -> str:
    """签发 legacy 形态 JWT(无 typ,30d)——仅供兼容性测试构造存量令牌。"""
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": subject, "role": role, "iat": now, "exp": now + timedelta(days=30)},
        settings.secret_key,
        algorithm="HS256",
    )


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as exc:
        raise AuthError("unauthorized", "无效或过期的令牌", 401) from exc


def decode_access_token(token: str) -> dict:
    """校验 access JWT;legacy(无 typ)放行,typ 不符拒绝。"""
    payload = _decode(token)
    if payload.get("typ") not in (None, "access"):
        raise AuthError("unauthorized", "无效的令牌类型", 401)
    return payload


def decode_email_verify_token(token: str) -> str:
    """校验邮箱验证令牌,返回 user_id;无效/过期 401。"""
    payload = _decode(token)
    if payload.get("typ") != "email_verify":
        raise AuthError("invalid_token", "验证链接无效", 400)
    return payload["sub"]


def create_email_verify_token(user_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": user_id, "typ": "email_verify", "iat": now, "exp": now + VERIFY_EMAIL_TTL},
        settings.secret_key,
        algorithm="HS256",
    )


# ── refresh(落库令牌族)──────────────────────────────────────

def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def is_refresh_shape(raw: str | None) -> bool:
    return bool(raw) and raw.startswith(REFRESH_PREFIX) and len(raw) == 43  # type: ignore[union-attr]


async def issue_refresh(
    session: AsyncSession, user_id: str, family_id: uuid.UUID | None = None,
    user_agent: str = "", ip: str = "",
) -> tuple[str, uuid.UUID]:
    """签发 refresh(新家族或续链),返回 (明文, family_id)。"""
    family = family_id or uuid.uuid4()
    raw = f"{REFRESH_PREFIX}{secrets.token_urlsafe(30)}"
    session.add(
        RefreshToken(
            user_id=uuid.UUID(user_id), family_id=family, token_hash=_hash(raw),
            expires_at=datetime.now(UTC) + REFRESH_TTL,
            user_agent=user_agent[:200], ip=ip[:64],
        )
    )
    await session.flush()
    return raw, family


async def rotate_refresh(session: AsyncSession, raw: str) -> tuple[str, str, uuid.UUID]:
    """校验并轮换:返回 (新明文, user_id, family_id)。

    - 无效/过期 → 401
    - 已被轮换过(revoked_at 非空)→ 重放信号,吊销全族后 401
    """
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw))
    )
    now = datetime.now(UTC)
    if row is None or row.expires_at < now:
        raise AuthError("unauthorized", "登录已过期,请重新登录", 401)
    if row.revoked_at is not None:
        # 重放已轮换令牌:该登录链全部作废(设计 018 §6);吊销先落库再抛
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.commit()
        raise AuthError("unauthorized", "检测到令牌重放,请重新登录", 401)
    row.revoked_at = now
    row.last_used_at = now
    new_raw, _ = await issue_refresh(
        session, str(row.user_id), family_id=row.family_id,
        user_agent=row.user_agent, ip=row.ip,
    )
    return new_raw, str(row.user_id), row.family_id


async def revoke_family(session: AsyncSession, raw: str) -> str | None:
    """按明文吊销其家族;返回 user_id(不存在返回 None)。"""
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw))
    )
    if row is None:
        return None
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return str(row.user_id)


async def user_for_refresh(session: AsyncSession, user_id: str) -> User:
    """refresh 后取用户;禁用账号按 401 处理(不泄露存在性)。"""
    user = await session.get(User, uuid.UUID(user_id))
    if user is None or user.disabled_at is not None:
        raise AuthError("unauthorized", "账号不可用", 401)
    return user


# ── 登录设备管理(M24 P3/需求 013 C1)───────────────────────

async def list_login_sessions(session: AsyncSession, user_id: str) -> list[dict]:
    """按令牌族聚合该用户的有效登录(设备视角)。

    返回:活跃族(未吊销且未过期,含最近活跃/首登/IP/UA 摘要)+ 最近失效族
    (登出/过期/重放吊销,作登录历史,取 10 条)。仅本人(user_id 过滤)。
    """
    from datetime import UTC, datetime

    rows = (
        await session.scalars(
            select(RefreshToken)
            .where(RefreshToken.user_id == uuid.UUID(user_id))
            .order_by(RefreshToken.created_at.desc())
            .limit(500)
        )
    ).all()
    now = datetime.now(UTC)
    families: dict[uuid.UUID, dict] = {}
    for r in rows:
        f = families.setdefault(
            r.family_id,
            {"family_id": str(r.family_id), "created_at": r.created_at, "active": False,
             "last_used_at": None, "ip": r.ip, "user_agent": r.user_agent[:60]},
        )
        f["created_at"] = min(f["created_at"], r.created_at)
        if r.last_used_at and (f["last_used_at"] is None or r.last_used_at > f["last_used_at"]):
            f["last_used_at"] = r.last_used_at
        if r.revoked_at is None and r.expires_at > now:
            f["active"] = True
    active = sorted(
        (f for f in families.values() if f["active"]),
        key=lambda f: f["last_used_at"] or f["created_at"],
        reverse=True,
    )
    history = sorted(
        (f for f in families.values() if not f["active"]),
        key=lambda f: f["last_used_at"] or f["created_at"],
        reverse=True,
    )[:10]
    return [{**f, "active": True} for f in active] + [
        {**f, "active": False} for f in history
    ]


async def revoke_family_by_id(session: AsyncSession, user_id: str, family_id: str) -> bool:
    """按 family_id 踢出该登录(全部 token 作废);越权/不存在返回 False。"""
    try:
        fid = uuid.UUID(family_id)
    except ValueError:
        return False
    row = await session.scalar(
        select(RefreshToken).where(
            RefreshToken.family_id == fid, RefreshToken.user_id == uuid.UUID(user_id)
        )
    )
    if row is None:
        return False
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == fid, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.commit()
    return True
