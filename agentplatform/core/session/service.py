"""会话服务(设计 004 §sessions / 005 §4)。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.session.model import Session


async def create_session(
    session: AsyncSession,
    plugin_id: uuid.UUID | None,
    title: str | None = None,
    user_id: str | None = None,
) -> Session:
    row = Session(plugin_id=plugin_id, title=title, user_id=user_id)
    session.add(row)
    await session.flush()
    return row


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> Session | None:
    return await session.get(Session, session_id)


async def list_sessions(
    session: AsyncSession, user_id: str | None = None
) -> list[Session]:
    stmt = select(Session).order_by(Session.updated_at.desc())
    rows = await session.scalars(stmt)
    return list(rows)
