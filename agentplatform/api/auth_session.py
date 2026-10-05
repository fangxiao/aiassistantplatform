"""会话签发(M24 P2/需求 013 B1/设计 018 §6):access + refresh(cookie)统一出口。

所有登录类端点(密码/GitHub/飞书)经 issue_session 下发双令牌;
refresh 仅走 httpOnly Cookie(Path=/api/auth),access 保持 Bearer 兼容 CLI。
"""

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.model import User
from agentplatform.core.auth.schemas import TokenOut, UserOut
from agentplatform.core.auth.tokens import REFRESH_PREFIX as _RF
from agentplatform.core.auth.tokens import create_access_token, issue_refresh

COOKIE_NAME = "rf"
COOKIE_PATH = "/api/auth"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30d,与 REFRESH_TTL 一致


def _cookie_secure() -> bool:
    """https 公网暴露时加 Secure;本地 http 保持可用。"""
    return (settings.public_api_base or "").startswith("https://")


def set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=COOKIE_MAX_AGE,
        path=COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)


def read_refresh_cookie(request: Request) -> str | None:
    raw = request.cookies.get(COOKIE_NAME)
    return raw if raw and raw.startswith(_RF) else None


async def issue_session(
    session: AsyncSession, user: User, request: Request, response: Response
) -> TokenOut:
    """签发 access(2h)+ refresh(30d,cookie),返回 TokenOut;提交 refresh 落库。"""
    token = create_access_token(str(user.id), user.role.value)
    raw, _ = await issue_refresh(
        session,
        str(user.id),
        user_agent=request.headers.get("user-agent", "")[:200],
        ip=request.client.host if request.client else "",
    )
    await session.commit()
    set_refresh_cookie(response, raw)
    return TokenOut(token=token, user=UserOut.model_validate(user))
