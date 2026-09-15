"""定时任务 API(M15,设计 011 §5)。

用户级定时任务 CRUD、手动触发、运行记录;全部按当前用户隔离。
错误统一 {error:{code,message}};配额/参数错误 400。
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.scheduler import service as scheduler_service
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


class TaskIn(BaseModel):
    """创建/编辑定时任务;kind=custom 必填 prompt,daily 必填 daily_at。"""

    name: str = Field(min_length=1, max_length=100)
    kind: str = "briefing"
    prompt: str = Field(default="", max_length=2000)  # custom 必填;模板任务可填补充要求
    schedule_type: str = "daily"
    daily_at: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    interval_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 30)
    plugin_id: uuid.UUID | None = None
    mounted_kb_ids: list[uuid.UUID] = []
    auto_save_kb: bool = False
    enabled: bool = True


class TaskOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    prompt: str
    schedule_type: str
    daily_at: str | None
    interval_minutes: int | None
    plugin_id: uuid.UUID | None
    mounted_kb_ids: list[uuid.UUID]
    auto_save_kb: bool
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_status: str
    last_error: str | None
    created_at: datetime


class RunOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    output: str | None
    session_id: uuid.UUID | None
    error: str | None


def _task_out(t: ScheduledTask) -> TaskOut:
    return TaskOut(
        id=t.id, name=t.name, kind=t.kind, prompt=t.prompt,
        schedule_type=t.schedule_type, daily_at=t.daily_at,
        interval_minutes=t.interval_minutes, plugin_id=t.plugin_id,
        mounted_kb_ids=[uuid.UUID(k) for k in (t.mounted_kb_ids or [])],
        auto_save_kb=t.auto_save_kb, enabled=t.enabled,
        last_run_at=t.last_run_at, next_run_at=t.next_run_at,
        last_status=t.last_status, last_error=t.last_error, created_at=t.created_at,
    )


def _run_out(r) -> RunOut:
    return RunOut(
        id=r.id, task_id=r.task_id, started_at=r.started_at, finished_at=r.finished_at,
        status=r.status, output=r.output, session_id=r.session_id, error=r.error,
    )


async def _get_owned_task(task_id: uuid.UUID, db, user: User) -> ScheduledTask:
    task = await scheduler_service.get_task(db, str(user.id), task_id)
    if task is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "任务不存在"}
        )
    return task


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[TaskOut]:
    """我的定时任务列表。"""
    return [_task_out(t) for t in await scheduler_service.list_tasks(db, str(user.id))]


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskIn,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskOut:
    """新建定时任务(配额校验;next_run_at 立即计算,不立即执行)。"""
    try:
        task = await scheduler_service.create_task(
            db, str(user.id),
            name=payload.name.strip() or "未命名任务",
            kind=payload.kind,
            prompt=payload.prompt,
            schedule_type=payload.schedule_type,
            daily_at=payload.daily_at,
            interval_minutes=payload.interval_minutes,
            plugin_id=payload.plugin_id,
            mounted_kb_ids=[str(k) for k in payload.mounted_kb_ids],
            auto_save_kb=payload.auto_save_kb,
            enabled=payload.enabled,
        )
    except scheduler_service.SchedulerError as exc:
        raise HTTPException(status_code=400, detail={"code": "scheduler_error", "message": str(exc)}) from exc
    await db.commit()
    return _task_out(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskIn,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> TaskOut:
    """编辑任务(配置变更后重算 next_run_at)。"""
    task = await _get_owned_task(task_id, db, user)
    task.name = payload.name.strip() or task.name
    task.kind = payload.kind
    task.prompt = payload.prompt
    task.schedule_type = payload.schedule_type
    task.daily_at = payload.daily_at
    task.interval_minutes = payload.interval_minutes
    task.plugin_id = payload.plugin_id
    task.mounted_kb_ids = [str(k) for k in payload.mounted_kb_ids]
    task.auto_save_kb = payload.auto_save_kb
    task.enabled = payload.enabled
    task.next_run_at = scheduler_service.compute_next_run(task, datetime.now())
    await db.commit()
    return _task_out(task)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    """删除任务(运行记录保留作审计)。"""
    ok = await scheduler_service.delete_task(db, str(user.id), task_id)
    if not ok:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "任务不存在"})
    await db.commit()
    return Response(status_code=204)


@router.post("/tasks/{task_id}/run", status_code=202)
async def run_task_now(
    task_id: uuid.UUID,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """手动跑一次(与到点自动运行同一路径,验收 8);运行中时 400。"""
    task = await _get_owned_task(task_id, db, user)
    try:
        run = await scheduler_service.trigger_run(db, task)
    except scheduler_service.SchedulerError as exc:
        raise HTTPException(status_code=400, detail={"code": "scheduler_error", "message": str(exc)}) from exc
    await db.commit()
    return {"run_id": str(run.id), "status": run.status}


@router.get("/tasks/{task_id}/runs", response_model=list[RunOut])
async def list_runs(
    task_id: uuid.UUID,
    limit: int = 10,
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunOut]:
    """任务运行记录(倒序)。"""
    runs = await scheduler_service.list_runs(db, str(user.id), task_id, limit)
    return [_run_out(r) for r in runs]


@router.get("/runs/latest", response_model=RunOut | None)
async def latest_success_run(
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> RunOut | None:
    """当前用户最近一次成功产出(工作台简报卡"自动生成"区数据源)。"""
    from sqlalchemy import select

    # 限定用户自己的任务;join task 过滤 user_id
    my_task_ids = select(ScheduledTask.id).where(ScheduledTask.user_id == str(user.id))
    row = await db.scalar(
        select(TaskRun)
        .where(
            TaskRun.task_id.in_(my_task_ids),
            TaskRun.status == "success",
            TaskRun.output.isnot(None),
        )
        .order_by(TaskRun.finished_at.desc().nullslast(), TaskRun.started_at.desc())
        .limit(1)
    )
    return _run_out(row) if row is not None else None
