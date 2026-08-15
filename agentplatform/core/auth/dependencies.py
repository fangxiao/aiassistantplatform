"""鉴权依赖:从 Bearer JWT 解析当前用户(M1)。

所有受保护业务 API 注入依赖 get_current_user;除 /auth/register、/auth/login 外
均需令牌(设计 005 §1 / §2)。错误走统一 401 信封。
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.model import User
from agentplatform.core.auth.service import decode_access_token
from agentplatform.core.db.session import get_session

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    """解析 Bearer JWT → 查库返回当前用户;缺失/无效抛 401。"""
    if credentials is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "缺少认证令牌"}
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.__dict__) from exc
    user = await session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "用户不存在"}
        )
    return user


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """解析 Bearer JWT; 缺失或无效时返回 None (供开放端点 / CLI 部署复用)。"""
    if credentials is None:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        sub = payload.get("sub")
        if not sub:
            return None
        return await session.get(User, sub)
    except Exception:  # noqa: BLE001
        return None