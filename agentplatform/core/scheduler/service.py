"""定时任务服务与调度器(M15,设计 011 §3)。

调度复用连接器模式(DB 持久化 + tick 扫描 + 启动恢复 + running 拒绝重入);
执行复用会话链路:自动创建会话 + run_agent 非流式聚合,产出落 task_runs。
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.scheduler.context import build_context, build_prompt
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun

logger = logging.getLogger(__name__)

TASK_KINDS = ("briefing", "inspection", "custom")


class SchedulerError(Exception):
    """定时任务业务错误(配额/参数)。"""


# ---------------------------------------------------------------- 下次运行时间


def compute_next_run(task: ScheduledTask, now: datetime) -> datetime | None:
    """纯函数:next_run_at(错过不补跑,自 now 顺延);无法解析的配置返回 None 并由调用方标失败。"""
    if task.schedule_type == "interval":
        minutes = task.interval_minutes or 0
        if minutes <= 0:
            return None
        return now + timedelta(minutes=minutes)
    if task.schedule_type == "daily":
        if not task.daily_at or ":" not in task.daily_at:
            return None
        try:
            hh, mm = (int(p) for p in task.daily_at.split(":", 1))
        except ValueError:
            return None
        candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    return None


# ---------------------------------------------------------------- 任务 CRUD


async def create_task(db: AsyncSession, user_id: str, **kwargs) -> ScheduledTask:
    """新建任务(配额校验;next_run_at 立即算出,不立即执行)。"""
    count = await db.scalar(
        select(func.count()).select_from(ScheduledTask).where(ScheduledTask.user_id == str(user_id))
    )
    if (count or 0) >= settings.scheduler_max_tasks_per_user:
        raise SchedulerError(f"定时任务数量达到上限 {settings.scheduler_max_tasks_per_user}")
    task = ScheduledTask(user_id=str(user_id), **kwargs)
    if task.kind not in TASK_KINDS:
        raise SchedulerError(f"不支持的任务类型: {task.kind!r}")
    if task.kind == "custom" and not task.prompt.strip():
        raise SchedulerError("自定义任务必须填写任务指令(prompt)")
    if task.schedule_type == "daily" and not task.daily_at:
        raise SchedulerError("每天调度必须指定执行时刻(daily_at)")
    if task.schedule_type == "interval" and not (task.interval_minutes and task.interval_minutes > 0):
        raise SchedulerError("间隔调度必须指定正整数分钟数")
    task.next_run_at = compute_next_run(task, datetime.now(UTC))
    db.add(task)
    await db.flush()
    return task


async def list_tasks(db: AsyncSession, user_id: str) -> list[ScheduledTask]:
    rows = await db.scalars(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == str(user_id))
        .order_by(ScheduledTask.created_at.desc())
    )
    return list(rows)


async def get_task(db: AsyncSession, user_id: str, task_id: uuid.UUID) -> ScheduledTask | None:
    task = await db.get(ScheduledTask, task_id)
    if task is None or task.user_id != str(user_id):
        return None
    return task


async def delete_task(db: AsyncSession, user_id: str, task_id: uuid.UUID) -> bool:
    task = await get_task(db, user_id, task_id)
    if task is None:
        return False
    await db.delete(task)  # task_runs 无 FK,保留审计
    await db.flush()
    return True


async def list_runs(db: AsyncSession, user_id: str, task_id: uuid.UUID, limit: int = 10) -> list[TaskRun]:
    task = await get_task(db, user_id, task_id)
    if task is None:
        return []
    rows = await db.scalars(
        select(TaskRun)
        .where(TaskRun.task_id == task_id)
        .order_by(TaskRun.started_at.desc())
        .limit(limit)
    )
    return list(rows)


# ---------------------------------------------------------------- 触发与执行


async def trigger_run(db: AsyncSession, task: ScheduledTask) -> TaskRun:
    """创建 running run 并后台执行;同任务已有 running run 时拒绝(防重入)。"""
    running = await db.scalar(
        select(func.count()).select_from(TaskRun).where(
            TaskRun.task_id == task.id, TaskRun.status == "running"
        )
    )
    if running:
        raise SchedulerError("该任务正在运行中")
    run = TaskRun(task_id=task.id, status="running")
    task.last_status = "running"
    task.last_error = None
    db.add(run)
    await db.flush()
    task_id, run_id = task.id, run.id
    t = asyncio.create_task(_execute_run(task_id, run_id))
    t.add_done_callback(_log_task_exception)
    return run


def _log_task_exception(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("scheduler: 任务执行异常 %s", task.exception())


async def _execute_run(task_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """后台执行体:独立 Session;自动会话 → 聚合 prompt → run_agent → 落产出。"""
    from agentplatform.core.chat.service import (
        make_llm_client,
        resource_ids_from_plugin,
    )
    from agentplatform.core.message.service import save_user_message
    from agentplatform.core.db.engine import SessionLocal
    from agentplatform.core.kb.search_tool import KB_SEARCH_TOOL_ID, resolve_allowed_kb_ids
    from agentplatform.core.plugin.loader import get_plugin
    from agentplatform.core.workbench.todo_tool import WORKBENCH_TODO_TOOL_ID

    async with SessionLocal() as db:
        task = await db.get(ScheduledTask, task_id)
        run = await db.get(TaskRun, run_id)
        if task is None or run is None:
            return
        try:
            # 1. 自动创建会话(以任务创建者身份)
            from agentplatform.core.session.service import create_session

            mounted = [uuid.UUID(k) for k in (task.mounted_kb_ids or [])]
            chat_sess = await create_session(db, plugin_id=task.plugin_id, user_id=str(task.user_id),
                                             mounted_kb_ids=mounted)

            # 2. 组装资源与权限(与会话链路同规则)
            plugin = await get_plugin(db, task.plugin_id) if task.plugin_id else None
            manifest = (plugin.manifest or {}) if plugin else None
            resource_ids = resource_ids_from_plugin(plugin) if plugin else []
            plugin_mounted = [uuid.UUID(k) for k in (getattr(plugin, "mounted_kb_ids", None) or [])] if plugin else []
            allowed_kb_ids = await resolve_allowed_kb_ids(
                db,
                mounted_kb_ids=[uuid.UUID(k) for k in (chat_sess.mounted_kb_ids or [])],
                plugin_manifest=manifest,
                plugin_mounted_kb_ids=plugin_mounted,
            )
            if allowed_kb_ids and KB_SEARCH_TOOL_ID not in resource_ids:
                resource_ids = [*resource_ids, KB_SEARCH_TOOL_ID]
            if WORKBENCH_TODO_TOOL_ID not in resource_ids:
                resource_ids = [*resource_ids, WORKBENCH_TODO_TOOL_ID]

            # 3. prompt:kind 模板 + 服务端聚合上下文
            context = await build_context(db, str(task.user_id), task.kind)
            prompt = build_prompt(task.kind, task.prompt, context)

            # 4. 运行 agent(非流式聚合;定时上下文无 SSE 消费者)
            client = await make_llm_client(db, (manifest or {}).get("model") if manifest else None)
            await save_user_message(db, chat_sess.id, prompt)
            from agentplatform.core.agent.loop import run_agent

            result = await asyncio.wait_for(
                run_agent(
                    db,
                    client,
                    resource_ids=resource_ids,
                    user_message=prompt,
                    history=[],
                    owner_id=str(task.user_id),
                    allowed_kb_ids=allowed_kb_ids,
                ),
                timeout=settings.scheduler_run_timeout_s,
            )
            output = (result.text or "").strip()
            if not output:
                raise RuntimeError("agent 未返回内容")

            run.output = output
            run.session_id = chat_sess.id
            run.status = "success"
            task.last_status = "success"
            await _maybe_autosave(db, task, chat_sess, output)
        except Exception as exc:  # noqa: BLE001  任何异常都落终态(验收 3)
            await db.rollback()
            run = await db.get(TaskRun, run_id)
            task = await db.get(ScheduledTask, task_id)
            assert run is not None and task is not None
            run.status = "failed"
            run.error = str(exc)[:500]
            task.last_status = "failed"
            task.last_error = str(exc)[:500]
        finally:
            task = await db.get(ScheduledTask, task_id)
            run = await db.get(TaskRun, run_id)
            if task is not None and run is not None:
                run.finished_at = datetime.now(UTC)
                task.last_run_at = run.finished_at
                task.next_run_at = compute_next_run(task, datetime.now(UTC))
                await db.commit()


async def _maybe_autosave(db: AsyncSession, task: ScheduledTask, chat_sess, output: str) -> None:
    """auto_save_kb:产出自动存知识库(用户首个可写库;失败不阻断运行成功)。"""
    if not task.auto_save_kb or not output:
        return
    try:
        from agentplatform.core.auth.model import User
        from agentplatform.core.kb import service as kb_service
        from sqlalchemy import select as _select

        owner = await db.scalar(_select(User).where(User.id == str(task.user_id)))
        if owner is None:
            return
        kb_rows = await kb_service.list_visible_kbs(db, str(task.user_id))
        target = None
        for kb in kb_rows:
            if await kb_service.can_write(db, kb, owner):
                target = kb
                break
        if target is None:
            return
        await kb_service.add_document_from_text(
            db, target, owner,
            title=f"定时任务 · {task.name} · {datetime.now(UTC).strftime('%m-%d %H:%M')}",
            content=output,
            source={"app": "scheduler", "session_id": str(chat_sess.id)},
        )
    except Exception as exc:  # noqa: BLE001  存库失败仅记录,不改运行状态
        logger.warning("scheduler: 自动存知识库失败 task=%s: %s", task.id, exc)
