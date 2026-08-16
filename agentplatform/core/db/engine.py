"""数据库引擎与会话工厂(async + asyncpg)。

单例 engine 供全应用复用;FastAPI 依赖见 session.py。
配置 idle_in_transaction_session_timeout 防止事务死锁挂起。
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentplatform.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "server_settings": {
            "idle_in_transaction_session_timeout": "30000",
            "statement_timeout": "30000",
        }
    },
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
