"""工作台 API(M14):待办 CRUD(前端 TodoCard 专用;AI 写入走 tool:workbench_todo)。

按当前用户隔离;错误统一 {error:{code,message}}。
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.workbench import service as workbench_service

router = APIRouter(prefix="/workbench", tags=["workbench"])


class TodoOut(BaseModel):
    id: uuid.UUID
    text: str
    done: bool
    origin: str
    created_at: datetime | None
    done_at: datetime | None


class TodoCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class TodoUpdate(BaseModel):
    done: bool


def _out(row) -> TodoOut:
    return TodoOut(
        id=row.id, text=row.text, done=row.done, origin=row.origin,
        created_at=row.created_at, done_at=row.done_at,
    )


@router.get("/todos", response_model=list[TodoOut])
async def list_todos(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[TodoOut]:
    """当前用户待办(未完成在前)。"""
    return [_out(r) for r in await workbench_service.list_todos(db, str(user.id))]


@router.post("/todos", response_model=TodoOut, status_code=201)
async def add_todo(
    payload: TodoCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TodoOut:
    try:
        row = await workbench_service.add_todo(db, str(user.id), payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": str(exc)}) from exc
    await db.commit()
    return _out(row)


@router.delete("/todos/completed")
async def clear_completed(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """清空已完成,返回删除条数。须注册在 /todos/{todo_id} 之前避免路径参数抢占。"""
    n = await workbench_service.clear_completed(db, str(user.id))
    await db.commit()
    return {"ok": True, "removed": n}


@router.patch("/todos/{todo_id}", response_model=TodoOut)
async def update_todo(
    todo_id: uuid.UUID,
    payload: TodoUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TodoOut:
    row = await workbench_service.set_done(db, str(user.id), todo_id, payload.done)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "待办不存在"})
    await db.commit()
    return _out(row)


@router.delete("/todos/{todo_id}", status_code=204)
async def remove_todo(
    todo_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    ok = await workbench_service.remove_todo(db, str(user.id), todo_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "待办不存在"})
    await db.commit()
    return Response(status_code=204)


@router.post("/todos/import")
async def import_local_todos(
    payload: list[str],
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """localStorage 旧数据一次性迁移导入(前端升级到云端存储时调用)。"""
    n = await workbench_service.import_todos(db, str(user.id), payload)
    await db.commit()
    return {"ok": True, "imported": n}
