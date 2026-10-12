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
from agentplatform.core.scheduler.context import (
    SCHEDULED_TASK_SYSTEM_PROMPT,
    build_context,
    build_prompt,
)
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun

logger = logging.getLogger(__name__)

TASK_KINDS = ("briefing", "inspection", "custom", "weekly_report", "freshness", "parent_report", "exam_prep")


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
        nxt = _next_local_time(now, task.daily_at)
        if nxt is None:
            return None
        return nxt
    if task.schedule_type == "weekly":
        # weekly_day: 1-7(周一到周日);时刻复用 daily_at(本地时区)
        if not task.weekly_day or not (1 <= task.weekly_day <= 7):
            return None
        nxt = _next_local_time(now, task.daily_at, force_future=False)
        if nxt is None:
            return None
        local = now.astimezone()
        days_ahead = (task.weekly_day - 1 - local.weekday()) % 7
        candidate = nxt + timedelta(days=days_ahead)
        if candidate <= local:
            candidate += timedelta(days=7)
        return candidate.astimezone(UTC)
    if task.schedule_type == "cron":
        # M33:cron 表达式(5 段标准;与 daily_at 同用服务器本地时区,用户视角一致)
        if not (task.cron_expr or "").strip():
            return None
        try:
            from croniter import croniter

            nxt = croniter(task.cron_expr.strip(), now.astimezone()).get_next(datetime)
            return nxt.astimezone(UTC)
        except Exception:  # noqa: BLE001  非法表达式由创建/编辑校验拦截,此处稳态兜底
            return None
    return None


def _next_local_time(now: datetime, hhmm: str | None, force_future: bool = True) -> datetime | None:
    """本地时区的下一个 hh:mm 时刻;force_future=False 时返回今天的该时刻(可能已过)。

    daily_at 为服务器本地时区时刻(用户视角);now 为 UTC——先转本地再算,
    否则 16:20 本地会变成 UTC16:20 = 次日 00:20(时区 bug 修复)。
    """
    if not hhmm or ":" not in hhmm:
        return None
    try:
        hh, mm = (int(p) for p in hhmm.split(":", 1))
    except ValueError:
        return None
    local = now.astimezone()
    candidate = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if force_future and candidate <= local:
        candidate += timedelta(days=1)
    return candidate


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
    if task.schedule_type == "weekly" and not (task.weekly_day and task.daily_at):
        raise SchedulerError("每周调度必须指定星期(weekly_day)与执行时刻(daily_at)")
    if task.schedule_type == "interval" and not (task.interval_minutes and task.interval_minutes > 0):
        raise SchedulerError("间隔调度必须指定正整数分钟数")
    if task.schedule_type == "cron":
        expr = (task.cron_expr or "").strip()
        if not expr:
            raise SchedulerError("cron 调度必须填写 cron 表达式(5 段标准格式)")
        try:
            from croniter import croniter

            croniter(expr)  # 仅校验合法性,不取值
        except Exception as exc:
            raise SchedulerError(f"cron 表达式不合法: {exc}") from exc
        task.cron_expr = expr
    task.next_run_at = compute_next_run(task, datetime.now(UTC))
    db.add(task)
    await db.flush()
    # M28 实体联动(需求 017 A1):定时任务天然是任务实体的一员
    from agentplatform.core.task.model import TaskEntity

    db.add(
        TaskEntity(
            user_id=uuid.UUID(str(user_id)), title=task.name, status="active",
            kind="scheduled", scheduled_task_id=task.id,
        )
    )
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
    # M28 联动:实体转 done(不级联删,交付物与会话保留)
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    from sqlalchemy import update as _upd

    from agentplatform.core.task.model import TaskEntity

    await db.execute(
        _upd(TaskEntity)
        .where(
            TaskEntity.scheduled_task_id == task_id,
            TaskEntity.status != "archived",
        )
        .values(status="done", completed_at=_dt.now(_UTC))
    )
    await db.flush()
    return True


# 上游错误 → 用户可读提示(20261010:SensitiveContentDetected 原文怼脸,用户无法理解)
_UPSTREAM_ERROR_HINTS: list[tuple[str, str]] = [
    ("SensitiveContentDetected", "上游模型安全审核拦截了本次请求(常见于误判)——请调整任务指令的措辞后重试,或在会话里换模型执行"),
    ("RateLimit", "上游模型限流——稍等片刻重试即可"),
    ("ConnectError", "上游模型网关连接失败(网络波动或服务不可用)——稍后重试"),
    ("timed out", "上游响应超时——可重试;若持续出现请缩小任务指令范围"),
]


def _friendly_run_error(raw: str) -> str:
    """已知上游错误翻译为人话 + 保留原文摘要;未知错误原样返回(截断)。"""
    for key, hint in _UPSTREAM_ERROR_HINTS:
        if key in raw:
            return f"{hint}(原始错误: {raw[:180]})"
    return raw[:500]


async def reap_zombie_runs(db: AsyncSession) -> int:
    """僵尸 run 清道夫(20261009 事故):running 但已结束(finished_at 非空)或
    超时 2 倍仍无终态的 run 一律判失败;同步任务 last_status。返回修复数。

    成因:后台 task 曾被 GC 回收 → CancelledError 逃逸 except → 只记 finished_at。
    根因已修(强引用),此处兜底历史数据与未知逃逸路径。
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt
    from datetime import timedelta as _td

    from agentplatform.config import settings as _settings

    cutoff = _dt.now(_UTC) - _td(seconds=_settings.scheduler_run_timeout_s * 2)
    zombies = (
        await db.scalars(
            select(TaskRun).where(
                TaskRun.status == "running",
                (TaskRun.finished_at.isnot(None)) | (TaskRun.started_at < cutoff),
            )
        )
    ).all()
    for z in zombies:
        z.status = "failed"
        z.error = (z.error or "")[:400] or "执行中断(僵尸 run 清道夫标记)"
        task = await db.get(ScheduledTask, z.task_id)
        if task is not None and task.last_status == "running":
            task.last_status = "failed"
            task.last_error = z.error
    if zombies:
        await db.commit()
    return len(zombies)


async def reap_expired_runs(db: AsyncSession) -> int:
    """M33:运行历史保留策略——清理超过保留期的 run 及其关联数据。

    每次运行自动建一个会话,多用户长期不清理会无限增长;交付物凭
    task_run_id/session_id 跳转(纯 UUID 引用无 FK),run 删了即死链,
    一并清理。删除顺序:交付物 → messages → interact_events → sessions
    → task_runs(FK 依赖序)。retention_days=0 表示永久保留。
    """
    from sqlalchemy import delete as _delete

    from agentplatform.core.artifacts.model import Artifact
    from agentplatform.core.interact.model import InteractEvent
    from agentplatform.core.message.model import Message
    from agentplatform.core.session.model import Session as ChatSession

    days = settings.scheduler_run_retention_days
    if days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    old_runs = (
        await db.scalars(select(TaskRun).where(TaskRun.started_at < cutoff))
    ).all()
    if not old_runs:
        return 0
    run_ids = [r.id for r in old_runs]
    session_ids = [r.session_id for r in old_runs if r.session_id]
    if run_ids:
        await db.execute(_delete(Artifact).where(Artifact.task_run_id.in_(run_ids)))
    if session_ids:
        await db.execute(_delete(Message).where(Message.session_id.in_(session_ids)))
        await db.execute(_delete(InteractEvent).where(InteractEvent.session_id.in_(session_ids)))
        await db.execute(_delete(ChatSession).where(ChatSession.id.in_(session_ids)))
    await db.execute(_delete(TaskRun).where(TaskRun.id.in_(run_ids)))
    await db.commit()
    logger.info("scheduler: 已清理 %d 条超过 %d 天的运行历史", len(old_runs), days)
    return len(old_runs)


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
    _BG_RUN_TASKS.add(t)  # 强引用:事件循环仅持弱引用,缺引用会被 GC 中途取消(20261009 僵尸 run 事故)
    t.add_done_callback(_log_task_exception)
    return run


# 后台执行任务强引用集合(完成即弃;防 GC 回收导致 CancelledError)
_BG_RUN_TASKS: set[asyncio.Task] = set()


def _log_task_exception(task: asyncio.Task) -> None:
    _BG_RUN_TASKS.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("scheduler: 任务执行异常 %s", task.exception())


async def _execute_run(task_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """后台执行体:独立 Session;自动会话 → 聚合 prompt → run_agent → 落产出。"""
    from agentplatform.core.chat.service import (
        make_llm_client,
        resource_ids_from_plugin,
    )
    from agentplatform.core.db.engine import SessionLocal
    from agentplatform.core.kb.search_tool import KB_SEARCH_TOOL_ID, resolve_allowed_kb_ids
    from agentplatform.core.message.service import save_user_message
    from agentplatform.core.plugin.loader import get_plugin

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
            # 会话即绑 + 提交检查点:运行中任务中心即可点开执行现场(M30 反馈)
            run.session_id = chat_sess.id
            await db.commit()
            task = await db.get(ScheduledTask, task_id)
            run = await db.get(TaskRun, run_id)
            if task is None or run is None:
                return

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
                session_user_id=str(task.user_id),
            )
            if allowed_kb_ids and KB_SEARCH_TOOL_ID not in resource_ids:
                resource_ids = [*resource_ids, KB_SEARCH_TOOL_ID]
            # 无人值守任务只注入"取外部信息/动作"类工具。workbench_todo 与 memory
            # 不再注入(20261011 词汇任务事故):任务 prompt 常是"每天生成X"这类持续性
            # 表述,模型看到 memory/todo 工具会改成"先记住偏好/建待办"或向用户确认,
            # 实测是把失败率从 0/5 拉到 4/5 与 3/5;插件 manifest 显式声明的不拦。
            from agentplatform.core.agent.http_action import HTTP_ACTION_TOOL_ID
            from agentplatform.core.agent.web_search import WEB_SEARCH_TOOL_ID
            from agentplatform.core.agent.web_search import is_configured as _search_ready

            if _search_ready() and WEB_SEARCH_TOOL_ID not in resource_ids:
                resource_ids = [*resource_ids, WEB_SEARCH_TOOL_ID]
            if HTTP_ACTION_TOOL_ID not in resource_ids:
                resource_ids = [*resource_ids, HTTP_ACTION_TOOL_ID]

            # 3. prompt:kind 模板 + 服务端聚合上下文
            context = await build_context(db, str(task.user_id), task.kind)
            # custom 注入运行环境:本地日期 + 上一次成功产出开头(供"每天一篇"
            # 类任务按期轮换、避免重复输出同一份内容)。当前 run 状态是 running,
            # 不会被 status='success' 过滤命中;首期无历史则为 None。
            prev_run = (
                await db.scalars(
                    select(TaskRun)
                    .where(TaskRun.task_id == task_id, TaskRun.status == "success")
                    .order_by(TaskRun.started_at.desc())
                    .limit(1)
                )
            ).first()
            prompt = build_prompt(
                task.kind,
                task.prompt,
                context,
                today=datetime.now(UTC).astimezone().date(),
                last_output=prev_run.output if prev_run else None,
            )

            # 4. 运行 agent(非流式聚合;定时上下文无 SSE 消费者)
            # 模型优先级(M33):任务级 model_override > 插件 manifest.model > 平台默认;
            # user_id 传入使用户自定义端点可被解析(与交互会话同规则)
            task_model = task.model_override or ((manifest or {}).get("model") if manifest else None)
            client = await make_llm_client(db, task_model, user_id=str(task.user_id))
            await save_user_message(db, chat_sess.id, prompt)
            from agentplatform.core.agent.loop import run_agent

            # M32(20261010 对标):失败自动重试——上游审核误杀/限流/网络抖动
            # 等瞬时错误占失败大头,重试成功率显著(WorkBuddy/千问同款行为);
            # attempt 落 run 行,UI 可见"重试过"。M33:次数与首退避可配,退避线性
            # (delay×attempt)——对网关长时间挂起类故障拉长间隔,不再固定 20s
            async def _run_once():
                return await asyncio.wait_for(
                    run_agent(
                        db,
                        client,
                        resource_ids=resource_ids,
                        user_message=prompt,
                        history=[],
                        owner_id=str(task.user_id),
                        allowed_kb_ids=allowed_kb_ids,
                        chat_session_id=str(chat_sess.id),
                        system_prompt=SCHEDULED_TASK_SYSTEM_PROMPT,
                        include_output_block=False,
                        allow_reasoning_fallback=False,
                    ),
                    timeout=settings.scheduler_run_timeout_s,
                )

            total_attempts = 1 + max(0, settings.scheduler_retry_attempts)
            result = None
            last_exc: Exception | None = None
            for attempt in range(1, total_attempts + 1):
                run.attempt = attempt
                try:
                    result = await _run_once()
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < total_attempts:
                        delay = max(1, settings.scheduler_retry_delay_s) * attempt
                        logger.warning(
                            "定时任务第 %d 次执行失败,%ds 后自动重试 task=%s: %s",
                            attempt, delay, task.id, str(exc)[:200],
                        )
                        await asyncio.sleep(delay)
            if result is None:
                assert last_exc is not None
                raise last_exc
            output = (result.text or "").strip()
            if not output:
                raise RuntimeError("agent 未返回内容")

            # 产出落会话(20261009 E2E 发现):非流式 run_agent 只返回文本不落
            # assistant 消息——执行现场此前只有指令没有产出,点开看不到结果
            from agentplatform.core.message.service import save_assistant_message

            await save_assistant_message(db, chat_sess.id, output)

            run.output = output
            run.session_id = chat_sess.id
            run.status = "success"
            # M33:token 用量落库(列一直在,此前从未写入,成本可观测是断的)
            run.tokens = result.usage_tokens
            # 成熟度④:通知出口推送(失败不影响任务)
            await _notify(db, task, output)
            # M22 P2-3:飞书推送(失败不影响任务)
            if getattr(task, "feishu_chat_id", None):
                try:
                    from agentplatform.core.channel.feishu import push_to_chat

                    await push_to_chat(
                        task.feishu_chat_id, f"⏰ {task.name}", output
                    )
                except Exception:  # noqa: BLE001
                    import logging as _lg

                    _lg.getLogger(__name__).warning(
                        "定时任务飞书推送失败 task=%s", task.id
                    )
            # P1 通知分级:产出首行 [ALERT] 标记 → alert=True 进通知;正常静默落卡
            run.alert = output.splitlines()[0].strip().startswith("[ALERT]") if output else False
            task.last_status = "success"
            # M36:学习活动记录(定时任务产出即视为一次学习行为)
            from agentplatform.core.study import service as study_service

            _subject_map = {"english": "english", "chinese": "chinese", "math": "math"}
            _subject = _subject_map.get(task.name.lower()[:8], "") or next(
                (s for s in _subject_map if s in task.name.lower()), "other"
            )
            await study_service.record(
                db, user_id=str(task.user_id),
                activity_type="scheduled_task", subject=_subject,
                count=1, source="scheduled_task",
                session_id=str(chat_sess.id),
            )

            # M25:成功产出登记交付物(kind=report,双引用跳会话;设计 019 §3.2)
            from datetime import datetime as _dt

            from agentplatform.core.artifacts.service import register_task_report

            await register_task_report(
                db,
                owner_id=str(task.user_id),
                title=f"{task.name} · {_dt.now(UTC).strftime('%m-%d')}",
                chat_session_id=str(chat_sess.id),
                task_run_id=str(run.id),
            )
            await _maybe_autosave(db, task, chat_sess, output)
        except Exception as exc:  # noqa: BLE001  任何异常都落终态(验收 3)
            await db.rollback()
            run = await db.get(TaskRun, run_id)
            task = await db.get(ScheduledTask, task_id)
            assert run is not None and task is not None
            friendly = _friendly_run_error(str(exc))
            run.status = "failed"
            run.error = friendly
            task.last_status = "failed"
            task.last_error = friendly
        finally:
            task = await db.get(ScheduledTask, task_id)
            run = await db.get(TaskRun, run_id)
            if task is not None and run is not None:
                run.finished_at = datetime.now(UTC)
                # 自愈:except Exception 抓不住 CancelledError 等逃逸路径——
                # 走到 finally 仍是 running 说明从未落终态,一律判失败并留痕
                if run.status == "running":
                    run.status = "failed"
                    run.error = (run.error or "")[:400] or "执行中断(后台任务被取消/回收,无终态)"
                    task.last_status = "failed"
                    task.last_error = run.error
                task.last_run_at = run.finished_at
                task.next_run_at = compute_next_run(task, datetime.now(UTC))
                await db.commit()


async def _maybe_autosave(db: AsyncSession, task: ScheduledTask, chat_sess, output: str) -> None:
    """auto_save_kb:产出自动存知识库(用户首个可写库;失败不阻断运行成功)。"""
    if not task.auto_save_kb or not output:
        return
    try:
        from sqlalchemy import select as _select

        from agentplatform.core.auth.model import User
        from agentplatform.core.kb import service as kb_service

        owner = await db.scalar(_select(User).where(User.id == str(task.user_id)))
        if owner is None:
            return
        kb_rows = await kb_service.list_visible_kbs(db, str(task.user_id))
        target = None
        # P1:优先任务声明的目标库(须存在且可写);缺省回退首个可写库
        if task.target_kb_id:
            target = next((kb for kb in kb_rows if kb.id == task.target_kb_id), None)
            if target is not None and not await kb_service.can_write(db, target, owner):
                target = None
        if target is None:
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


async def _notify(db, task: ScheduledTask, output: str) -> None:
    """按任务 notify 配置推送产出。

    产品化:优先 channel_ids(平台级/个人级通道,NotificationChannel);
    inline webhook/email 兼容保留(快速临时用)。失败不影响任务本身。
    """
    from sqlalchemy import select as _select

    from agentplatform.core.notify import service as notify_service
    from agentplatform.core.notify.model import NotificationChannel

    cfg = task.notify or {}
    text = f"⏰ 定时任务「{task.name}」产出:\n\n{output[:1500]}"
    channels: list = []
    ids = cfg.get("channel_ids") or []
    if ids:
        rows = await db.scalars(
            _select(NotificationChannel).where(
                NotificationChannel.id.in_(ids),
                NotificationChannel.enabled.is_(True),
                (NotificationChannel.user_id.is_(None))
                | (NotificationChannel.user_id == str(task.user_id)),
            )
        )
        channels = list(rows)
    for ch in channels:
        await notify_service.deliver(ch, text)
    # inline 兼容(M34:分派进 notify 服务,新增微信 Server酱/pushplus 格式)
    if cfg.get("webhook"):
        await notify_service.send_task_webhook(
            str(cfg["webhook"]), str(cfg.get("webhook_payload") or ""), text, task.name
        )
    if cfg.get("email"):
        notify_service.send_email(str(cfg["email"]), f"AgentPlatform · {task.name}", text)



