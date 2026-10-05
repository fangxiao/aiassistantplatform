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


class TasksPanelOut(BaseModel):
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
    """任务中心聚合:进行中(活跃会话 + running runs)/ 定时任务 / 交付物。

    三路各一条查询,均按当前用户隔离(需求 014 A1/A4)。
    """
    from datetime import UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from sqlalchemy import select as _sel

    from agentplatform.core.artifacts.model import Artifact
    from agentplatform.core.message.model import Message
    from agentplatform.core.scheduler.model import ScheduledTask, TaskRun
    from agentplatform.core.session.model import Session as ChatSession

    uid = user.id
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
    tasks = (
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
        for t in tasks
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

    return TasksPanelOut(running=running, scheduled=scheduled, artifacts=artifacts)
