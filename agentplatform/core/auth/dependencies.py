"""鉴权依赖:从 Bearer JWT 解析当前用户(M1)+ 角色层级门槛(015 §3,ADR 0008)。

所有受保护业务 API 注入依赖 get_current_user;除 /auth/register、/auth/login 外
均需令牌(设计 005 §1 / §2)。错误走统一 401 信封。
角色层级:admin ⊃ developer ⊃ user,业务代码用 require_admin/require_developer,
不直接比较 role。
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.auth.service import decode_access_token
from agentplatform.core.db.session import get_session

_bearer = HTTPBearer(auto_error=False)


def is_admin(user: User) -> bool:
    """平台管理员。"""
    return user.role == UserRole.admin


def is_developer(user: User) -> bool:
    """开发者能力(admin 亦为真,层级制)。"""
    return user.role in (UserRole.developer, UserRole.admin)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """解析 Bearer JWT / PAT → 查库返回当前用户;缺失/无效抛 401;禁用 403。

    M24:JWT 失败后回落 PAT(ap_ 前缀,sha256 查 personal_access_tokens)。
    """
    if credentials is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "缺少认证令牌"}
        )
    user = None
    try:
        payload = decode_access_token(credentials.credentials)
        user = await session.get(User, payload.get("sub"))
    except AuthError:
        raw = credentials.credentials
        if raw.startswith("ap_"):
            from datetime import UTC as _UTC, datetime as _dt
            from hashlib import sha256 as _sha

            from sqlalchemy import select as _sel

            from agentplatform.core.auth.oauth_model import PersonalAccessToken

            pat = await session.scalar(
                _sel(PersonalAccessToken).where(
                    PersonalAccessToken.token_hash == _sha(raw.encode()).hexdigest(),
                    PersonalAccessToken.revoked_at.is_(None),
                )
            )
            if pat is not None:
                pat.last_used_at = _dt.now(_UTC)
                user = await session.get(User, pat.user_id)
        if user is None:
            raise HTTPException(
                status_code=401, detail={"code": "unauthorized", "message": "令牌无效或已过期"}
            )
    if user is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "用户不存在"}
        )
    if user.disabled_at is not None:
        raise HTTPException(
            status_code=403, detail={"code": "forbidden", "message": "账号已被禁用"}
        )
    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """解析 Bearer JWT; 缺失或无效时返回 None (供开放端点复用)。"""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        sub = payload.get("sub")
        if not sub:
            return None
        user = await session.get(User, sub)
        if user is None or user.disabled_at is not None:
            return None
        return user
    except Exception:  # noqa: BLE001
        return None


def _forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "forbidden", "message": message})


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """平台管理员门槛(用户管理/LLM 端点/通知渠道/全局洞察/审批)。"""
    if not is_admin(user):
        raise _forbidden("仅平台管理员可执行此操作")
    return user


async def require_developer(user: User = Depends(get_current_user)) -> User:
    """开发者门槛(部署/调试/发布申请);admin 层级放行。"""
    if not is_developer(user):
        raise _forbidden("仅开发者可执行此操作")
    return user