"""定时任务测试(M15,T15.6):next_run 计算/CRUD 校验/配额/is_due/API。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.scheduler import service as scheduler_service
from agentplatform.core.scheduler.model import ScheduledTask
from agentplatform.core.scheduler.scheduler import is_due
from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user


@pytest.fixture
async def dev_user(session: AsyncSession):
    return await create_user(session, f"sdev-{uuid.uuid4()}@test.dev", "password123", UserRole.developer)


@pytest.fixture
async def normal_user(session: AsyncSession):
    return await create_user(session, f"su-{uuid.uuid4()}@test.dev", "password123", UserRole.user)


def _task(**kw) -> ScheduledTask:
    base = dict(
        id=uuid.uuid4(), user_id="u1", name="t", kind="briefing", prompt="",
        schedule_type="daily", daily_at="08:00", enabled=True,
    )
    base.update(kw)
    return ScheduledTask(**base)


class TestComputeNextRun:
    def test_daily_future_today(self) -> None:
        now = datetime(2026, 9, 15, 7, 0, tzinfo=UTC)
        nxt = scheduler_service.compute_next_run(_task(daily_at="08:00"), now)
        assert nxt == datetime(2026, 9, 15, 8, 0, tzinfo=UTC)

    def test_daily_past_rolls_to_tomorrow(self) -> None:
        """错过不补跑:今天 08:00 已过 → 顺延明天(验收 2)。"""
        now = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
        nxt = scheduler_service.compute_next_run(_task(daily_at="08:00"), now)
        assert nxt == datetime(2026, 9, 16, 8, 0, tzinfo=UTC)

    def test_interval(self) -> None:
        now = datetime(2026, 9, 15, 9, 0, tzinfo=UTC)
        nxt = scheduler_service.compute_next_run(
            _task(schedule_type="interval", interval_minutes=30, daily_at=None), now
        )
        assert nxt == now + timedelta(minutes=30)

    def test_invalid_returns_none(self) -> None:
        now = datetime.now(UTC)
        assert scheduler_service.compute_next_run(_task(daily_at="bad"), now) is None
        assert scheduler_service.compute_next_run(
            _task(schedule_type="interval", interval_minutes=0, daily_at=None), now
        ) is None


class TestIsDue:
    def test_semantics(self) -> None:
        now = datetime.now(UTC)
        t = _task(next_run_at=now - timedelta(minutes=1))
        assert is_due(t, now)
        assert not is_due(t, now - timedelta(minutes=5))  # 未到期
        t2 = _task(next_run_at=None)
        assert not is_due(t2, now)  # 从未排期
        t3 = _task(enabled=False, next_run_at=now - timedelta(minutes=1))
        assert not is_due(t3, now)  # 停用
        assert not is_due(t, now, running_count=1)  # 运行中不重复触发


class TestTaskService:
    async def test_create_validation(self, session: AsyncSession, dev_user) -> None:
        with pytest.raises(scheduler_service.SchedulerError):  # custom 缺 prompt
            await scheduler_service.create_task(
                session, str(dev_user.id), name="x", kind="custom", prompt="  ",
                schedule_type="daily", daily_at="08:00",
            )
        with pytest.raises(scheduler_service.SchedulerError):  # daily 缺时刻
            await scheduler_service.create_task(
                session, str(dev_user.id), name="x", kind="briefing", prompt="",
                schedule_type="daily", daily_at=None,
            )
        ok = await scheduler_service.create_task(
            session, str(dev_user.id), name="晨报", kind="briefing", prompt="",
            schedule_type="daily", daily_at="08:30",
        )
        assert ok.next_run_at is not None and ok.enabled

    async def test_quota(self, session: AsyncSession, dev_user) -> None:
        """验收 7:每用户任务数上限。"""
        old = settings.scheduler_max_tasks_per_user
        settings.scheduler_max_tasks_per_user = 2
        try:
            for i in range(2):
                await scheduler_service.create_task(
                    session, str(dev_user.id), name=f"t{i}", kind="briefing", prompt="",
                    schedule_type="interval", interval_minutes=60,
                )
            with pytest.raises(scheduler_service.SchedulerError, match="上限"):
                await scheduler_service.create_task(
                    session, str(dev_user.id), name="t3", kind="briefing", prompt="",
                    schedule_type="interval", interval_minutes=60,
                )
        finally:
            settings.scheduler_max_tasks_per_user = old

    async def test_user_isolation(self, session: AsyncSession, dev_user, normal_user) -> None:
        """验收 5:非创建者不可见/不可删。"""
        t = await scheduler_service.create_task(
            session, str(dev_user.id), name="私有任务", kind="briefing", prompt="",
            schedule_type="interval", interval_minutes=60,
        )
        assert await scheduler_service.get_task(session, str(normal_user.id), t.id) is None
        assert not await scheduler_service.delete_task(session, str(normal_user.id), t.id)
        assert await scheduler_service.list_runs(session, str(normal_user.id), t.id) == []


@pytest.mark.asyncio
class TestSchedulerApi:
    async def test_task_lifecycle(self, client: AsyncClient) -> None:
        # 创建
        r = await client.post(
            "/api/scheduler/tasks",
            json={"name": "每日晨报", "kind": "briefing", "schedule_type": "daily", "daily_at": "08:00"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["last_status"] == "never" and body["next_run_at"] is not None
        tid = body["id"]

        # 参数错误 → 400
        r_bad = await client.post(
            "/api/scheduler/tasks",
            json={"name": "x", "kind": "custom", "prompt": "", "schedule_type": "daily", "daily_at": "08:00"},
        )
        assert r_bad.status_code == 400

        # 编辑重算 next_run_at
        r2 = await client.patch(
            f"/api/scheduler/tasks/{tid}",
            json={"name": "晨报改", "kind": "briefing", "prompt": "", "schedule_type": "daily", "daily_at": "09:30"},
        )
        assert r2.status_code == 200
        assert r2.json()["name"] == "晨报改"

        # 手动跑一次 → 202(后台连接运行库,测试环境空转不等待)
        r3 = await client.post(f"/api/scheduler/tasks/{tid}/run")
        assert r3.status_code == 202, r3.text

        # 运行记录 + latest
        r4 = await client.get(f"/api/scheduler/tasks/{tid}/runs")
        assert r4.status_code == 200
        r5 = await client.get("/api/scheduler/runs/latest")
        assert r5.status_code == 200

        # 删除
        r6 = await client.delete(f"/api/scheduler/tasks/{tid}")
        assert r6.status_code == 204
        assert (await client.get("/api/scheduler/tasks")).json() == []
