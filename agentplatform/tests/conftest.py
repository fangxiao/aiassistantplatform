"""共享测试基础设施:真实 PostgreSQL 测试库引擎与会话 fixture。

PG 不可达时跳过依赖它的测试(测试不要求常驻基础设施);
NullPool 避免 asyncpg 连接跨事件循环复用(循环绑定)。
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User  # noqa: F401  表注册进 metadata
from agentplatform.core.auth.service import create_access_token, create_user
from agentplatform.core.db.base import Base
from agentplatform.core.db.session import get_session
from agentplatform.core.interact.model import InteractEvent  # noqa: F401
from agentplatform.core.llm.model import LlmEndpoint  # noqa: F401
from agentplatform.core.message.model import Message  # noqa: F401
from agentplatform.core.plugin.model import Plugin  # noqa: F401
from agentplatform.core.registry.model import SkillTool  # noqa: F401
from agentplatform.core.session.model import Session as ChatSession  # noqa: F401
from agentplatform.config import settings
from agentplatform.main import app

ADMIN_URL = "postgresql+asyncpg://agentplatform:agentplatform@localhost:5432/agentplatform"
TEST_URL = "postgresql+asyncpg://agentplatform:agentplatform@localhost:5432/agentplatform_test"


async def _ensure_test_db() -> None:
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": "agentplatform_test"},
            )
            if not exists:
                await conn.execute(text('CREATE DATABASE "agentplatform_test"'))
    finally:
        await admin.dispose()
    # 知识库(M12)需要 pgvector 扩展(按库安装);在 test 库上启用
    test_admin = create_async_engine(TEST_URL, isolation_level="AUTOCOMMIT")
    try:
        async with test_admin.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    finally:
        await test_admin.dispose()


@pytest.fixture(autouse=True)
def _isolate_dev_settings() -> "object":
    """强制本机开发开关在测试中关闭,隔离开发者 ~/.agentplatform/.env 的污染。

    例如 BROWSER_DEV_ROUTE_ANY=true 会让 BrowserBridge 跨用户回退路由,
    导致 bridge/tunnel 的严格鉴权单测随本机配置飘移。
    """
    settings.browser_dev_route_any = False
    yield


@pytest.fixture(scope="session")
async def db_engine():
    try:
        await _ensure_test_db()
    except Exception as exc:  # noqa: BLE001  PG 不可达则跳过整套 DB 测试
        pytest.skip(f"PostgreSQL 不可用,跳过数据库测试: {exc}")
    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # 打磨①:混合检索依赖 pg_trgm(contrib 自带;生产由迁移 d6f3a8b21c95 建)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as s:
        # 每个测试独立数据:清空所有业务表(倒序以满足外键约束)
        for table in reversed(Base.metadata.sorted_tables):
            await s.execute(table.delete())
        await s.commit()
        yield s


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """API 测试客户端:get_session 依赖覆盖为测试库会话。

    同时覆盖 get_current_user 固定返回一个测试用户,使现有业务 API 测试
    默认携带合法身份;认证本身的 401/注册/登录见 test_auth_api。
    """
    user = await create_user(session, f"unit-{id(session)}@test.dev", "password123")
    await session.commit()

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_token(session: AsyncSession) -> str:
    """创建测试用户,返回合法 JWT(供受保护 API 测试携带)。"""
    import uuid

    user = await create_user(session, f"user-{uuid.uuid4()}@test.dev", "password123")
    await session.commit()
    return create_access_token(str(user.id), user.role.value)


@pytest.fixture
async def auth_headers(auth_token: str) -> dict[str, str]:
    """带 Bearer 的请求头。"""
    return {"Authorization": f"Bearer {auth_token}"}
