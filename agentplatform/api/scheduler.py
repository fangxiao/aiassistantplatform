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
    target_kb_id: uuid.UUID | None = None  # P1:自动存库目标(空=回退首个可写库)
    notify: dict = {}  # 成熟度④:{webhook?, webhook_payload?: feishu|raw, email?}
    feishu_chat_id: str | None = Field(default=None, max_length=120)  # M22 P2-3 应用内机器人推送目标
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
    target_kb_id: uuid.UUID | None
    notify: dict
    feishu_chat_id: str | None = None
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
        auto_save_kb=t.auto_save_kb, target_kb_id=t.target_kb_id, notify=t.notify or {},
        feishu_chat_id=t.feishu_chat_id, enabled=t.enabled,
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
            target_kb_id=payload.target_kb_id,
            notify=payload.notify,
            feishu_chat_id=payload.feishu_chat_id,
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
    task.target_kb_id = payload.target_kb_id
    task.notify = payload.notify
    task.feishu_chat_id = payload.feishu_chat_id
    task.enabled = payload.enabled
    from datetime import UTC as _UTC

    task.next_run_at = scheduler_service.compute_next_run(task, datetime.now(_UTC))
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


# ── 推送目标与测试(M30:任务推送体验)────────────────────────


@router.get("/push-targets")
async def push_targets(
    db=Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """飞书推送目标(已有会话,选择代替手填 chat_id)+ SMTP 状态。

    push_to_chat 遍历在岗机器人试发,目标只需 chat_id;会话列表来自
    channel_sessions(与机器人对话过的群/人)。
    """
    from sqlalchemy import Text as _Text
    from sqlalchemy import select as _sel

    from agentplatform.config import settings
    from agentplatform.core.channel.model import ChannelSession
    from agentplatform.core.session.model import Session as ChatSession
    from agentplatform.core.auth.model import User as _U

    rows = (
        await db.execute(
            _sel(ChannelSession, ChatSession, _U.email)
            .join(ChatSession, ChannelSession.session_id == ChatSession.id)
            .outerjoin(_U, ChatSession.user_id == _U.id.cast(_Text))
            .where(ChannelSession.channel == "feishu")
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
    ).all()
    chats = [
        {
            "chat_id": cs.chat_id,
            "label": f"{s.title or '飞书会话'} · {email or '未知用户'}",
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for cs, s, email in rows
    ]
    from agentplatform.core.channel.feishu import _GATEWAYS

    bots = [
        {"app_id": g.get("app_id", ""), "name": g.get("name", "")}
        for g in _GATEWAYS.values()
        if g.get("client")
    ]
    return {
        "feishu_chats": chats,
        "feishu_bots_online": bots,
        "smtp_configured": bool(settings.notify_smtp_host),
    }


@router.post("/push-test")
async def push_test(
    payload: dict,
    user: User = Depends(get_current_user),
) -> dict:
    """向目标会话发一条测试卡片(限频 1 次/10 秒/用户)。"""
    import time

    chat_id = (payload or {}).get("chat_id", "")
    if not chat_id:
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "缺少 chat_id"})
    now = time.monotonic()
    last = _PUSH_TEST_TS.get(str(user.id), 0.0)
    if now - last < 10:
        raise HTTPException(status_code=429, detail={"code": "rate_limited", "message": "测试太频繁,稍后再试"})
    _PUSH_TEST_TS[str(user.id)] = now

    from agentplatform.core.channel.feishu import push_to_chat

    ok = await push_to_chat(chat_id, "✅ 推送测试", "AgentPlatform 定时任务推送通道正常。")
    if not ok:
        raise HTTPException(status_code=502, detail={"code": "push_failed", "message": "推送失败:会话不存在或机器人不在该会话中"})
    return {"ok": True}


_PUSH_TEST_TS: dict[str, float] = {}
