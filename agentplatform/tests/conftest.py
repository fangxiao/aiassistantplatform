"""共享测试基础设施:真实 PostgreSQL 测试库引擎与会话 fixture。

PG 不可达时跳过依赖它的测试(测试不要求常驻基础设施);
NullPool 避免 asyncpg 连接跨事件循环复用(循环绑定)。
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from agentplatform.core.db.base import Base
from agentplatform.core.registry.model import SkillTool  # noqa: F401  表注册进 metadata

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


@pytest.fixture(scope="session")
async def db_engine():
    try:
        await _ensure_test_db()
    except Exception as exc:  # noqa: BLE001  PG 不可达则跳过整套 DB 测试
        pytest.skip(f"PostgreSQL 不可用,跳过数据库测试: {exc}")
    engine = create_async_engine(TEST_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
