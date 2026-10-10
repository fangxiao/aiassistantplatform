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


# ── 任务面板(M25/需求 014/设计 019 §4)──────────────────────


class RunningItem(BaseModel):
    kind: str  # session / run
    id: str
    title: str
    detail: str = ""
    session_id: str | None = None  # 跳转续问用
    started_at: datetime | None = None
    updated_at: datetime | None = None


class ScheduledItem(BaseModel):
    id: str
    name: str
    kind: str
    next_run_at: datetime | None
    last_status: str


class ArtifactItem(BaseModel):
    id: str
    kind: str  # html / image / report
    title: str
    created_at: datetime
    session_id: str | None
    signed_url: str | None  # 文件类展示时现签(签名有 TTL,不落库)
    content: str | None = None  # report 类带产出摘要(存 KB 用,截断)


class TaskEntityItem(BaseModel):
    """任务实体(M28/需求 017):列表优先区,聚合三栏为「未提升会话」视图。"""

    id: str
    title: str
    status: str  # active/done/archived
    kind: str  # manual/scheduled
    session_id: str | None
    scheduled_task_id: str | None = None  # kind=scheduled 时关联执行配置(运行状态徽标)
    latest_session_id: str | None = None  # 定时任务最近一次执行的会话(点开看执行情况)
    artifact_count: int = 0
    created_at: datetime
    completed_at: datetime | None


class TasksPanelOut(BaseModel):
    tasks: list[TaskEntityItem] = []  # M28:实体区在前
    done_tasks: list[TaskEntityItem] = []  # M30:已完成/已归档(折叠区)
    running: list[RunningItem]
    scheduled: list[ScheduledItem]
    artifacts: list[ArtifactItem]


def _first_text(blocks: list | None) -> str:
    """blocks 首个 text 内容摘要(面板一行展示用)。"""
    if not blocks:
        return ""
    for b in blocks:
        if not isinstance(b, dict):
            continue
        text = b.get("text")
        if not text and isinstance(b.get("data"), dict):
            text = b["data"].get("text")
        if text:
            return str(text)[:60]
    return ""


@router.get("/tasks", response_model=TasksPanelOut)
async def tasks_panel(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TasksPanelOut:
    """任务中心聚合:任务实体(M28)/ 进行中(活跃会话+running runs)/ 定时任务 / 交付物。

    各路一条查询,均按当前用户隔离(需求 014 A1/A4 + 017 A3)。
    """
    from datetime import UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from sqlalchemy import func as _func
    from sqlalchemy import select as _sel

    from agentplatform.core.artifacts.model import Artifact
    from agentplatform.core.message.model import Message
    from agentplatform.core.scheduler.model import ScheduledTask, TaskRun
    from agentplatform.core.session.model import Session as ChatSession
    from agentplatform.core.task.model import TaskEntity

    uid = user.id

    # 任务实体区(M28):active 优先展示,置顶最近创建
    entities = (
        await db.scalars(
            _sel(TaskEntity)
            .where(TaskEntity.user_id == uid, TaskEntity.status == "active")
            .order_by(TaskEntity.created_at.desc())
            .limit(20)
        )
    ).all()
    done_entities = (
        await db.scalars(
            _sel(TaskEntity)
            .where(TaskEntity.user_id == uid, TaskEntity.status != "active")
            .order_by(TaskEntity.completed_at.desc().nulls_last())
            .limit(15)
        )
    ).all()
    all_entities = [*entities, *done_entities]
    # 定时任务最近一次执行的会话(任务行点击直达执行现场,M30 用户反馈)
    _sched_ids = [e.scheduled_task_id for e in all_entities if e.scheduled_task_id]
    latest_run_session: dict[str, str | None] = {}
    if _sched_ids:
        _runs = (
            await db.scalars(
                _sel(TaskRun)
                .where(TaskRun.task_id.in_(_sched_ids))
                .order_by(TaskRun.started_at.desc())
                .limit(120)
            )
        ).all()
        for r in _runs:
            latest_run_session.setdefault(str(r.task_id), str(r.session_id) if r.session_id else None)
    # 交付物计数键:manual 用 e.session_id;scheduled 用最近执行会话(20261010 表格
    # 第四列修复——此前 scheduled 实体 session 为空,计数恒 0,📦 永不渲染)
    _count_keys: set[str] = set()
    for e in all_entities:
        if e.session_id:
            _count_keys.add(str(e.session_id))
        elif e.scheduled_task_id:
            _sid = latest_run_session.get(str(e.scheduled_task_id))
            if _sid:
                _count_keys.add(_sid)
    ent_counts = (
        dict(
            (await db.execute(
                _sel(Artifact.session_id, _func.count())
                .where(Artifact.session_id.in_([uuid.UUID(k) for k in _count_keys]))
                .group_by(Artifact.session_id)
            )).all()
        )
        if _count_keys
        else {}
    )

    def _entity_item(e: TaskEntity) -> TaskEntityItem:
        count_sid = (
            str(e.session_id) if e.session_id
            else (latest_run_session.get(str(e.scheduled_task_id)) if e.scheduled_task_id else None)
        )
        return TaskEntityItem(
            id=str(e.id), title=e.title, status=e.status, kind=e.kind,
            session_id=str(e.session_id) if e.session_id else None,
            scheduled_task_id=str(e.scheduled_task_id) if e.scheduled_task_id else None,
            latest_session_id=(
                latest_run_session.get(str(e.scheduled_task_id))
                if e.scheduled_task_id
                else None
            ),
            artifact_count=int(ent_counts.get(uuid.UUID(count_sid), 0)) if count_sid else 0,
            created_at=e.created_at, completed_at=e.completed_at,
        )

    tasks = [_entity_item(e) for e in entities]
    done_tasks = [_entity_item(e) for e in done_entities]
    since = _dt.now(UTC) - _td(minutes=30)

    # 进行中:近 30 分钟有消息的会话(取 5)
    recent_sessions = (
        await db.scalars(
            _sel(ChatSession)
            .where(ChatSession.user_id == str(uid), ChatSession.updated_at >= since)
            .order_by(ChatSession.updated_at.desc())
            .limit(5)
        )
    ).all()
    running: list[RunningItem] = [
        RunningItem(
            kind="session",
            id=str(s.id),
            title=s.title or "未命名会话",
            updated_at=s.updated_at,
        )
        for s in recent_sessions
    ]
    if running:
        # 批量取每个会话最后一条消息摘要(一条查询)
        sids = [uuid.UUID(r.id) for r in running]
        msgs = (
            await db.scalars(
                _sel(Message)
                .where(Message.session_id.in_(sids), Message.role == "assistant")
                .order_by(Message.created_at.desc())
                .limit(30)
            )
        ).all()
        latest: dict[str, str] = {}
        for m in msgs:  # created_at 倒序,首见即最新
            latest.setdefault(str(m.session_id), _first_text(m.blocks))
        for r in running:
            r.detail = latest.get(r.id, "")

    # 进行中:running 的定时任务运行(取 5)
    runs = (
        await db.execute(
            _sel(TaskRun, ScheduledTask)
            .join(ScheduledTask, TaskRun.task_id == ScheduledTask.id)
            .where(TaskRun.status == "running", ScheduledTask.user_id == str(uid))
            .order_by(TaskRun.started_at.desc())
            .limit(5)
        )
    ).all()
    running.extend(
        RunningItem(
            kind="run",
            id=str(run.id),
            title=task.name,
            detail="定时任务执行中",
            session_id=str(run.session_id) if run.session_id else None,
            started_at=run.started_at,
        )
        for run, task in runs
    )

    # 定时任务:enabled 按下次运行排序(取 8)
    sched_rows = (
        await db.scalars(
            _sel(ScheduledTask)
            .where(ScheduledTask.user_id == str(uid), ScheduledTask.enabled.is_(True))
            .order_by(ScheduledTask.next_run_at.asc().nulls_first())
            .limit(8)
        )
    ).all()
    scheduled = [
        ScheduledItem(
            id=str(t.id), name=t.name, kind=t.kind,
            next_run_at=t.next_run_at, last_status=t.last_status,
        )
        for t in sched_rows
    ]

    # 交付物:最近 30 条,文件类现签 URL;report 类带产出摘要(存 KB 用)
    from agentplatform.api.files import sign_file_path
    from agentplatform.config import settings

    arts = (
        await db.scalars(
            _sel(Artifact)
            .where(Artifact.user_id == uid)
            .order_by(Artifact.created_at.desc())
            .limit(30)
        )
    ).all()
    report_contents: dict[str, str] = {}
    report_run_ids = [a.task_run_id for a in arts if a.kind == "report" and a.task_run_id]
    if report_run_ids:
        report_rows = (
            await db.scalars(_sel(TaskRun).where(TaskRun.id.in_(report_run_ids)))
        ).all()
        report_contents = {str(r.id): (r.output or "")[:4000] for r in report_rows}
    artifacts = [
        ArtifactItem(
            id=str(a.id), kind=a.kind, title=a.title,
            created_at=a.created_at, session_id=str(a.session_id) if a.session_id else None,
            signed_url=(
                (settings.public_api_base.rstrip("/") if settings.public_api_base else "")
                + sign_file_path(a.path)
                if a.path
                else None
            ),
            content=report_contents.get(str(a.task_run_id)) if a.kind == "report" else None,
        )
        for a in arts
    ]

    return TasksPanelOut(tasks=tasks, done_tasks=done_tasks, running=running, scheduled=scheduled, artifacts=artifacts)
