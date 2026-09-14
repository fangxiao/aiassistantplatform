"""个人工作台服务:待办 CRUD(设计 010;前端 TodoCard 与 AI 工具共用的权威存储)。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.workbench.model import WorkbenchTodo


async def list_todos(db: AsyncSession, user_id: str) -> list[WorkbenchTodo]:
    """当前用户待办:未完成在前,组内按创建时间倒序。"""
    rows = await db.scalars(
        select(WorkbenchTodo)
        .where(WorkbenchTodo.user_id == str(user_id))
        .order_by(WorkbenchTodo.done, WorkbenchTodo.created_at.desc())
    )
    return list(rows)


async def add_todo(
    db: AsyncSession, user_id: str, text: str, *, origin: str = "manual"
) -> WorkbenchTodo:
    text = (text or "").strip()
    if not text:
        raise ValueError("待办内容不能为空")
    if len(text) > 500:
        text = text[:500]
    row = WorkbenchTodo(user_id=str(user_id), text=text, origin=origin)
    db.add(row)
    await db.flush()
    return row


async def get_todo(db: AsyncSession, user_id: str, todo_id: uuid.UUID) -> WorkbenchTodo | None:
    row = await db.get(WorkbenchTodo, todo_id)
    if row is None or row.user_id != str(user_id):  # 跨用户不可见不可改
        return None
    return row


async def set_done(
    db: AsyncSession, user_id: str, todo_id: uuid.UUID, done: bool
) -> WorkbenchTodo | None:
    row = await get_todo(db, user_id, todo_id)
    if row is None:
        return None
    row.done = done
    row.done_at = datetime.now(UTC) if done else None
    await db.flush()
    return row


async def remove_todo(db: AsyncSession, user_id: str, todo_id: uuid.UUID) -> bool:
    row = await get_todo(db, user_id, todo_id)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def clear_completed(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        sa_delete(WorkbenchTodo).where(
            WorkbenchTodo.user_id == str(user_id), WorkbenchTodo.done.is_(True)
        )
    )
    return result.rowcount or 0


async def import_todos(
    db: AsyncSession, user_id: str, texts: list[str]
) -> int:
    """localStorage 一次性迁移导入(前端检测到本地旧数据时调用)。"""
    n = 0
    for text in texts:
        if (text or "").strip():
            await add_todo(db, user_id, text)
            n += 1
    return n
