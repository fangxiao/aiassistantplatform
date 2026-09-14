"""连接器轮询调度器(设计 009 §6,需求 U3/验收 4)。

进程内 asyncio 单例:每 tick 扫描到期源(手动/轮询间隔),逐个触发同步。
启动即扫一轮(重启恢复,状态在 DB,天然续跑)。多 worker 重复触发由
"同 source running run 拒绝"去重,分布式锁留待规模化。
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from agentplatform.config import settings
from agentplatform.core.kb.model import KbDataSource

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def is_due(source: KbDataSource, now: datetime) -> bool:
    """纯函数:源是否到期应同步(active + 设了轮询 + 首次或超间隔)。"""
    if source.status != "active" or source.poll_interval_minutes is None:
        return False
    if source.last_sync_at is None:
        return True
    return now - source.last_sync_at >= timedelta(minutes=source.poll_interval_minutes)


async def _tick() -> int:
    """扫描到期源并触发;返回本轮触发的源数(供测试断言)。"""
    from agentplatform.core.db.engine import SessionLocal
    from agentplatform.core.kb.connectors import service as connector_service

    triggered = 0
    async with SessionLocal() as db:
        rows = await db.scalars(select(KbDataSource))
        due = [s for s in rows if is_due(s, datetime.now(UTC))]
        for source in due:
            try:
                run = await connector_service.trigger_sync(db, source)
                await db.commit()
                logger.info("connector: 调度触发同步 source=%s run=%s", source.id, run.id)
                triggered += 1
            except Exception as exc:  # noqa: BLE001  单源失败不影响其他源(验收 8)
                logger.warning("connector: 调度触发失败 source=%s: %s", source.id, exc)
    return triggered


async def _loop() -> None:
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("connector: 调度 tick 异常")
        await asyncio.sleep(settings.connector_scheduler_tick_seconds)


def start() -> None:
    """lifespan 启动:立即扫一轮 + 周期 tick。"""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
        logger.info("connector: 调度器已启动(tick=%ss)", settings.connector_scheduler_tick_seconds)


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
        logger.info("connector: 调度器已停止")
