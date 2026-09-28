"""认证服务:密码哈希 + JWT 签发 + 用户 CRUD(M1)。

- 密码:passlib CryptContext(bcrypt);明文不落库。
- 令牌:python-jose HS256,以 settings.secret_key 签名。
"""

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.errors import AuthError
from agentplatform.core.auth.model import User, UserRole

# bcrypt 自带随机会话盐(salt);后端 1.7.4 + bcrypt<4.1(兼容性见 pyproject 注释)
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACCESS_TOKEN_EXPIRE = timedelta(days=30)


def hash_password(password: str) -> str:
    """bcrypt 哈希。"""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文与哈希是否匹配。"""
    return _pwd_context.verify(password, password_hash)


def create_access_token(subject: str, role: str) -> str:
    """签发 JWT(HS256)。subject 为用户 id,exp 默认 24h。"""
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE,
    }
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """解码并校验 JWT;无效/过期抛 AuthError(401)。"""
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as exc:
        raise AuthError("unauthorized", "无效或过期的令牌", 401) from exc


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return (await session.scalars(stmt)).first()


async def create_user(
    session: AsyncSession,
    email: str,
    password: str,
    role: UserRole = UserRole.user,
) -> User:
    """注册用户;email 查重,冲突抛 AuthError(409)。只存哈希。"""
    email = email.lower().strip()
    if await get_user_by_email(session, email):
        raise AuthError("email_exists", "该邮箱已注册", 409)
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate(
    session: AsyncSession, email: str, password: str
) -> User | None:
    """校验登录;返回用户或 None(不区分"邮箱不存在/密码错误",避免用户枚举)。

    禁用账号(disabled_at 非空,015 §2)一律拒绝,同样不区分凭据对错。
    """
    user = await get_user_by_email(session, email.lower().strip())
    if user is None or user.disabled_at is not None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def ensure_initial_admin(session: AsyncSession) -> None:
    """bootstrap 首个 admin(015 §6):INITIAL_ADMIN_EMAIL 存在则升级,否则创建。

    幂等:已是 admin 无操作;未配置环境变量则跳过。仅创建场景用
    INITIAL_ADMIN_PASSWORD,未提供时随机生成并日志提示(提示一次性)。
    """
    import logging
    import secrets

    from agentplatform.config import settings

    if not settings.initial_admin_email:
        return
    log = logging.getLogger(__name__)
    email = settings.initial_admin_email.lower().strip()
    user = await get_user_by_email(session, email)
    if user is None:
        password = settings.initial_admin_password or secrets.token_urlsafe(16)
        user = await create_user(session, email, password, UserRole.admin)
        if settings.initial_admin_password:
            log.info("bootstrap: 已创建初始管理员 %s", email)
        else:
            log.warning("bootstrap: 已创建初始管理员 %s,临时密码: %s(请尽快登录修改)", email, password)
    elif user.role != UserRole.admin:
        user.role = UserRole.admin
        log.info("bootstrap: 已将既有用户 %s 升级为 admin", email)
    else:
        return
    await session.flush()