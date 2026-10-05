"""认证 API(设计 005 §2)。

POST /auth/register  注册,201 返回用户;成功后异步发验证邮件(M24 P2)
POST /auth/login     登录,返回 {token, user};双令牌:access 2h + refresh cookie
POST /auth/refresh   cookie 轮换 refresh → 新双令牌(M24 P2)
POST /auth/logout    吊销令牌族 + 清 cookie(M24 P2)
POST /auth/verify-email / resend-verification 邮箱验证(M24 P2)
GET  /auth/me        当前用户(受保护)
错误走统一 {error: {code, message}} 信封(AuthError / HTTPException)。
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.api.auth_session import (
    clear_refresh_cookie,
    issue_session,
    read_refresh_cookie,
    set_refresh_cookie,
)
from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)
from agentplatform.core.auth.service import authenticate, create_user
from agentplatform.core.auth.tokens import (
    create_access_token,
    create_email_verify_token,
    decode_email_verify_token,
    revoke_family,
    rotate_refresh,
    user_for_refresh,
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
    from agentplatform.api.auth_ext import (
        _client_ip,
        allow_ip_auth,
        allow_ip_register,
        consume_invite,
    )
    from agentplatform.config import settings

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
    # 验证邮件线程投递(SMTP 未配置/失败不阻断注册;M24 P2)
    _send_verification_email_bg(str(user.id), user.email)
    return user


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """登录;凭据错误 401;限频+账号锁定(M24/需求 013 A5)。"""
    from agentplatform.api.auth_ext import (
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
    return await issue_session(session, user, request, response)


# ── 双令牌会话(M24 P2/设计 018 §6)──────────────────────────


@router.post("/refresh", response_model=TokenOut)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> TokenOut:
    """cookie 轮换 refresh → 新 access + 新 refresh;重放已轮换令牌吊销全族。"""
    raw = read_refresh_cookie(request)
    if raw is None:
        raise HTTPException(
            status_code=401, detail={"code": "unauthorized", "message": "缺少登录凭据"}
        )
    try:
        new_raw, user_id, _family = await rotate_refresh(session, raw)
        user = await user_for_refresh(session, user_id)
        await session.commit()
    except AuthError as exc:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
        ) from exc
    set_refresh_cookie(response, new_raw)
    return TokenOut(
        token=create_access_token(str(user.id), user.role.value),
        user=UserOut.model_validate(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """吊销 refresh 令牌族 + 清 cookie;前端另清 localStorage。"""
    raw = read_refresh_cookie(request)
    if raw is not None:
        await revoke_family(session, raw)
        await session.commit()
    clear_refresh_cookie(response)
    return {"ok": True}


# ── 邮箱验证(M24 P2/设计 018 §9)────────────────────────────


class VerifyEmailIn(BaseModel):
    token: str


def _send_verification_email_bg(user_id: str, email: str) -> None:
    """线程投递验证邮件;SMTP 未配置跳过,失败仅日志。"""
    import logging
    import threading

    from agentplatform.config import settings
    from agentplatform.core.notify.service import send_email

    if not settings.notify_smtp_host:
        return
    token = create_email_verify_token(user_id)
    link = f"{settings.public_web_base.rstrip('/')}/auth?verify_token={token}"
    body = (
        "欢迎使用 AgentPlatform!\n\n"
        "请点击以下链接完成邮箱验证(24 小时内有效):\n"
        f"{link}\n\n"
        "如果这不是你的操作,请忽略本邮件。"
    )

    def _deliver() -> None:
        try:
            send_email(email, "AgentPlatform 邮箱验证", body)
        except Exception:
            logging.getLogger(__name__).warning("验证邮件投递失败 to=%s", email, exc_info=True)

    threading.Thread(target=_deliver, daemon=True).start()


@router.post("/verify-email")
async def verify_email(
    payload: VerifyEmailIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """验证令牌落库;重复验证幂等成功。"""
    try:
        user_id = decode_email_verify_token(payload.token)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
        ) from exc
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=400, detail={"code": "invalid_token", "message": "验证链接无效"})
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        await session.commit()
    return {"ok": True, "email": user.email}


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """重发验证邮件;限频 1 次/分钟、3 次/天(进程内,与限频同策略)。"""
    from agentplatform.core.auth.ratelimit import allow_resend

    if user.email_verified_at is not None:
        return {"ok": True, "message": "邮箱已验证"}
    if not allow_resend(str(user.id)):
        raise HTTPException(
            status_code=429, detail={"code": "rate_limited", "message": "发送过于频繁,请稍后再试"}
        )
    _send_verification_email_bg(str(user.id), user.email)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    """当前用户信息(需 Bearer 令牌)。"""
    return user

# ── 登录设备管理(M24 P3/需求 013 C1)────────────────────────


@router.get("/sessions")
async def login_sessions(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """登录设备列表(活跃族 + 最近失效历史);仅本人。"""
    from agentplatform.core.auth.tokens import list_login_sessions

    return await list_login_sessions(session, str(user.id))


@router.delete("/sessions/{family_id}")
async def kick_login(
    family_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """踢出一个登录(吊销其令牌族);不存在/越权 404。"""
    from agentplatform.core.auth.tokens import revoke_family_by_id

    ok = await revoke_family_by_id(session, str(user.id), family_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "登录不存在"})
    return {"ok": True}
