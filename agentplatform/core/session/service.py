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
    mounted_kb_ids: list[uuid.UUID] | None = None,
) -> Session:
    row = Session(
        plugin_id=plugin_id,
        title=title,
        user_id=user_id,
        mounted_kb_ids=[str(k) for k in (mounted_kb_ids or [])],
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> Session | None:
    return await session.get(Session, session_id)


async def list_sessions(
    session: AsyncSession, user_id: str | None = None
) -> list[Session]:
    stmt = select(Session)
    if user_id is not None:
        stmt = stmt.where(Session.user_id == user_id)
    stmt = stmt.order_by(Session.updated_at.desc())
    rows = await session.scalars(stmt)
    return list(rows)


async def delete_session(session: AsyncSession, session_id: uuid.UUID) -> bool:
    row = await session.get(Session, session_id)
    if row is None:
        return False
    from sqlalchemy import delete

    from agentplatform.core.message.model import Message

    await session.execute(delete(Message).where(Message.session_id == session_id))
    await session.delete(row)
    await session.flush()
    return True



async def update_session_title(
    session: AsyncSession, session_id: uuid.UUID, title: str
) -> Session | None:
    row = await session.get(Session, session_id)
    if row is None:
        return None
    row.title = title
    await session.flush()
    await session.refresh(row)
    return row


async def update_session(
    session: AsyncSession,
    session_id: uuid.UUID,
    *,
    title: str | None = None,
    mounted_kb_ids: list[uuid.UUID] | None = None,
) -> Session | None:
    """按需更新标题与挂载知识库(M12);mounted_kb_ids 传 [] 表示清空。"""
    row = await session.get(Session, session_id)
    if row is None:
        return None
    if title is not None:
        row.title = title
    if mounted_kb_ids is not None:
        row.mounted_kb_ids = [str(k) for k in mounted_kb_ids]  # JSONB 存字符串形式,读侧转 UUID
    await session.flush()
    await session.refresh(row)
    return row


