"""定时任务调度器循环(M15,设计 011 §3)。

模式与连接器调度器同源:60s tick 扫 enabled 且到期(且无 running run)的任务
触发执行;启动即扫一轮(重启恢复);并发上限,超出顺延下个 tick;错过不补跑。
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from agentplatform.config import settings
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun
from agentplatform.core.scheduler.service import compute_next_run, trigger_run

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def is_due(task: ScheduledTask, now: datetime, running_count: int = 0) -> bool:
    """纯函数:任务是否到期应触发(active + 到期 + 无运行中实例)。"""
    if not task.enabled or task.next_run_at is None:
        return False
    if running_count > 0:
        return False
    return task.next_run_at <= now


async def _tick() -> int:
    """扫描到期任务并触发;返回本轮触发数(供测试断言)。"""
    from agentplatform.core.db.engine import SessionLocal

    triggered = 0
    async with SessionLocal() as db:
        # 全局并发上限:已有运行中 run 数
        running = await db.scalar(select(func.count()).select_from(TaskRun).where(TaskRun.status == "running"))
        slots = max(0, settings.scheduler_max_concurrent - (running or 0))
        if slots == 0:
            return 0
        now = datetime.now(UTC)
        rows = await db.scalars(
            select(ScheduledTask).where(ScheduledTask.enabled.is_(True)).order_by(ScheduledTask.next_run_at)
        )
        for task in rows:
            if slots == 0:
                break
            running_for_task = await db.scalar(
                select(func.count()).select_from(TaskRun).where(
                    TaskRun.task_id == task.id, TaskRun.status == "running"
                )
            )
            if is_due(task, now, running_for_task or 0):
                try:
                    await trigger_run(db, task)
                    await db.commit()
                    triggered += 1
                    slots -= 1
                except Exception as exc:  # noqa: BLE001  单任务失败不影响其他(验收 8)
                    logger.warning("scheduler: 触发失败 task=%s: %s", task.id, exc)
    return triggered


async def _loop() -> None:
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001  调度循环永不退出
            logger.exception("scheduler: 调度 tick 异常")
        await asyncio.sleep(settings.scheduler_tick_seconds)


def start() -> None:
    """lifespan 启动:立即扫一轮(重启恢复,验收 2)+ 周期 tick。"""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
        logger.info("scheduler: 定时任务调度器已启动(tick=%ss)", settings.scheduler_tick_seconds)


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        logger.info("scheduler: 定时任务调度器已停止")
