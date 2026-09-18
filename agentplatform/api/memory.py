"""长期记忆 REST API(M15 P1 打磨:记忆管理面板)。

用户查看/删除自己的记忆(透明度与隐私);AI 写入走 tool:memory,共用一份存储。
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.memory import service as memory_service
from agentplatform.core.memory.model import UserMemory

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryOut(BaseModel):
    id: uuid.UUID
    content: str
    created_at: datetime | None


def _out(row: UserMemory) -> MemoryOut:
    return MemoryOut(id=row.id, content=row.content, created_at=row.created_at)


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[MemoryOut]:
    """我的全部记忆(新→旧)。"""
    return [_out(r) for r in await memory_service.list_memories(db, str(user.id))]


@router.post("/memories", response_model=MemoryOut, status_code=201)
async def add_memory(
    payload: dict,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> MemoryOut:
    """手动添加一条记忆(内容 1-200 字)。"""
    try:
        row = await memory_service.add_memory(db, str(user.id), str(payload.get("content") or ""))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "validation_error", "message": str(exc)}
        ) from exc
    await db.commit()
    return _out(row)


@router.delete("/memories/{memory_id}", status_code=204)
async def remove_memory(
    memory_id: uuid.UUID,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
):
    ok = await memory_service.remove_memory(db, str(user.id), memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "记忆不存在"})
    await db.commit()


@router.delete("/memories")
async def clear_memories(
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """清空全部记忆。"""
    n = await memory_service.clear_all(db, str(user.id))
    await db.commit()
    return {"ok": True, "removed": n}
