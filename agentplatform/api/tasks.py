"""任务实体 API(M28/需求 017/设计 022 §3)。

会话提升为任务(409 幂等拒绝)/ 实体列表 / 状态流转 / 删除(不级联会话与交付物)。
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.artifacts.model import Artifact
from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.session.model import Session as ChatSession
from agentplatform.core.task.model import TaskEntity

router = APIRouter(prefix="/tasks", tags=["tasks"])

_STATUSES = ("active", "done", "archived")


class TaskEntityOut(BaseModel):
    id: str
    title: str
    status: str
    kind: str
    session_id: str | None
    scheduled_task_id: str | None
    created_at: datetime
    completed_at: datetime | None
    artifact_count: int = 0


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: str | None = None


def _out(e: TaskEntity, artifact_count: int = 0) -> TaskEntityOut:
    return TaskEntityOut(
        id=str(e.id), title=e.title, status=e.status, kind=e.kind,
        session_id=str(e.session_id) if e.session_id else None,
        scheduled_task_id=str(e.scheduled_task_id) if e.scheduled_task_id else None,
        created_at=e.created_at, completed_at=e.completed_at,
        artifact_count=artifact_count,
    )


async def _owned(db: AsyncSession, user: User, task_id: uuid.UUID) -> TaskEntity:
    row = await db.get(TaskEntity, task_id)
    if row is None or str(row.user_id) != str(user.id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "任务不存在"})
    return row


@router.post("/from-session/{sid}", response_model=TaskEntityOut, status_code=201)
async def promote_session(
    sid: uuid.UUID,
    payload: TaskPatch | None = None,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskEntityOut:
    """会话提升为任务(需求 017 A2);同会话重复提升 409。"""
    sess = await db.get(ChatSession, sid)
    if sess is None or str(sess.user_id) != str(user.id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "会话不存在"})
    dup = await db.scalar(select(TaskEntity).where(TaskEntity.session_id == sid))
    if dup is not None:
        raise HTTPException(
            status_code=409, detail={"code": "already_promoted", "message": "该会话已是任务"}
        )
    entity = TaskEntity(
        user_id=user.id,
        title=(payload.title if payload and payload.title else (sess.title or "未命名任务"))[:120],
        kind="manual",
        session_id=sid,
    )
    db.add(entity)
    await db.commit()
    cnt = await db.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.session_id == sid)
    )
    return _out(entity, int(cnt or 0))


@router.get("", response_model=list[TaskEntityOut])
async def list_tasks(
    status: str = "active",
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[TaskEntityOut]:
    """任务实体列表;?status=active|done|archived(默认 active)。"""
    if status not in _STATUSES:
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "status 取值 active/done/archived"})
    rows = (
        await db.scalars(
            select(TaskEntity)
            .where(TaskEntity.user_id == user.id, TaskEntity.status == status)
            .order_by(
                TaskEntity.completed_at.desc().nulls_first()
                if status != "active" else TaskEntity.created_at.desc()
            )
            .limit(50)
        )
    ).all()
    if not rows:
        return []
    counts = dict(
        (await db.execute(
            select(Artifact.session_id, func.count())
            .where(Artifact.session_id.in_([r.session_id for r in rows if r.session_id]))
            .group_by(Artifact.session_id)
        )).all()
    )
    return [
        _out(r, int(counts.get(r.session_id, 0)) if r.session_id else 0) for r in rows
    ]


@router.patch("/{task_id}", response_model=TaskEntityOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskPatch,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskEntityOut:
    """改名/状态流转(active↔done↔archived);done 记 completed_at。"""
    entity = await _owned(db, user, task_id)
    if payload.title:
        entity.title = payload.title
    if payload.status:
        if payload.status not in _STATUSES:
            raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "status 取值 active/done/archived"})
        entity.status = payload.status
        entity.completed_at = datetime.now(UTC) if payload.status == "done" else None
    await db.commit()
    cnt = (
        await db.scalar(
            select(func.count()).select_from(Artifact).where(Artifact.session_id == entity.session_id)
        )
        if entity.session_id
        else 0
    )
    return _out(entity, int(cnt or 0))


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    """仅删实体(会话与交付物保留;需求 017 A4)。"""
    entity = await _owned(db, user, task_id)
    await db.delete(entity)
    await db.commit()
