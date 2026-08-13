"""数据库引擎与会话工厂(async + asyncpg)。

单例 engine 供全应用复用;FastAPI 依赖见 session.py。
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentplatform.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
