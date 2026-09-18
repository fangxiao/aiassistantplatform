"""长期记忆服务(M15 P1):用户记忆的增删查(工具与注入共用)。"""

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.memory.model import UserMemory


async def list_memories(db: AsyncSession, user_id: str, limit: int | None = None) -> list[UserMemory]:
    """用户记忆,新→旧;limit 缺省全部(上限受写入侧控制)。"""
    rows = await db.scalars(
        select(UserMemory)
        .where(UserMemory.user_id == str(user_id))
        .order_by(UserMemory.created_at.desc())
    )
    return list(rows)


async def add_memory(db: AsyncSession, user_id: str, content: str) -> UserMemory:
    """新增记忆(内容清洗 + 每用户上限;超出时淘汰最旧)。"""
    content = (content or "").strip()
    if not content:
        raise ValueError("记忆内容不能为空")
    if len(content) > 200:
        content = content[:200]
    count = await db.scalar(
        select(func.count()).select_from(UserMemory).where(UserMemory.user_id == str(user_id))
    )
    if (count or 0) >= settings.memory_max_per_user:
        oldest = await db.scalar(
            select(UserMemory)
            .where(UserMemory.user_id == str(user_id))
            .order_by(UserMemory.created_at.asc())
            .limit(1)
        )
        if oldest is not None:
            await db.delete(oldest)
    row = UserMemory(user_id=str(user_id), content=content)
    db.add(row)
    await db.flush()
    return row


async def remove_memory(db: AsyncSession, user_id: str, memory_id: uuid.UUID) -> bool:
    row = await db.get(UserMemory, memory_id)
    if row is None or row.user_id != str(user_id):
        return False
    await db.delete(row)
    await db.flush()
    return True


async def clear_all(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        sa_delete(UserMemory).where(UserMemory.user_id == str(user_id))
    )
    return result.rowcount or 0


async def memories_for_prompt(db: AsyncSession, user_id: str, limit: int = 20) -> list[str]:
    """注入 system prompt 的记忆文本(最近 limit 条)。"""
    rows = await list_memories(db, str(user_id), limit=limit)
    return [r.content for r in rows]
