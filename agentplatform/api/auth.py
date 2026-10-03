"""认证 API(设计 005 §2)。

POST /auth/register  注册,201 返回用户
POST /auth/login     登录,返回 {token, user}
GET  /auth/me        当前用户(受保护)
错误走统一 {error: {code, message}} 信封(AuthError / HTTPException)。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)
from agentplatform.core.auth.service import (
    authenticate,
    create_access_token,
    create_user,
)
from agentplatform.core.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_error_to_http(exc: AuthError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )


@router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """注册新用户;email 冲突 409;邀请码制+限频(M24/需求 013)。

    角色收紧(2026-09-17):自选 developer 仅在 settings.allow_self_promote_developer
    显式开启(本地开发)时生效;默认一律注册为普通 user,防止接口自行提权。
    """
    from agentplatform.config import settings

    from agentplatform.api.auth_ext import allow_ip_auth, allow_ip_register, consume_invite, _client_ip

    ip = _client_ip(request)
    if not allow_ip_auth(ip) or not allow_ip_register(ip):
        raise HTTPException(
            status_code=429, detail={"code": "rate_limited", "message": "操作过于频繁,请稍后再试"}
        )
    if settings.invite_required:
        if not getattr(payload, "invite_code", ""):
            raise HTTPException(
                status_code=403, detail={"code": "invite_required", "message": "注册需邀请码(向管理员索取)"}
            )
        await consume_invite(session, payload.invite_code)
    role = payload.role
    if role == UserRole.developer and not settings.allow_self_promote_developer:
        role = UserRole.user
    try:
        user = await create_user(session, payload.email, payload.password, role)
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc
    # 冷启动:预置平台向导会话(失败静默)
    from agentplatform.core.onboarding import seed_onboarding

    await seed_onboarding(session, str(user.id))
    await session.commit()
    return user


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """登录;凭据错误 401;限频+账号锁定(M24/需求 013 A5)。"""
    from agentplatform.api.auth_ext import (  # noqa: F401
        _client_ip,
        account_locked,
        allow_ip_auth,
        clear_login_fail,
        record_login_fail,
    )

    ip = _client_ip(request)
    if not allow_ip_auth(ip):
        raise HTTPException(
            status_code=429, detail={"code": "rate_limited", "message": "尝试过于频繁,请 1 分钟后再试"}
        )
    if account_locked(payload.email):
        raise HTTPException(
            status_code=429, detail={"code": "account_locked", "message": "连续失败过多,账号锁定 15 分钟"}
        )
    user = await authenticate(session, payload.email, payload.password)
    if user is None:
        record_login_fail(payload.email)
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "邮箱或密码错误"},
        )
    clear_login_fail(payload.email)
    token = create_access_token(str(user.id), user.role.value)
    return TokenOut(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    """当前用户信息(需 Bearer 令牌)。"""
    return user