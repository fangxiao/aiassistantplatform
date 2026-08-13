"""FastAPI 依赖:请求级数据库会话。"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.db.engine import SessionLocal


async def get_session() -> AsyncIterator[AsyncSession]:
    """路由依赖:每个请求一个会话,用后自动关闭。"""
    async with SessionLocal() as session:
        yield session
