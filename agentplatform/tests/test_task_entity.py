"""M28 任务实体化测试(需求 017/设计 022)。

覆盖:会话提升(409 幂等/标题默认/artifacts 归集计数)、状态流转(done 记时/
archived 不在默认列表)、DELETE 不级联会话、scheduler 联动(建任务建实体/删任务
转 done)、聚合端点实体区。
"""

import uuid

from agentplatform.core.artifacts.model import Artifact
from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.auth.service import create_user
from agentplatform.core.scheduler.service import create_task as create_scheduled
from agentplatform.core.scheduler.service import delete_task as delete_scheduled
from agentplatform.core.session.model import Session as ChatSession
from agentplatform.core.task.model import TaskEntity
from agentplatform.main import app


async def _ctx(session, email="task@test.dev") -> tuple[User, ChatSession]:
    user = await create_user(session, email, "password123")
    sess = ChatSession(user_id=str(user.id), title="评审会话")
    session.add(sess)
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    return user, sess


async def test_promote_session_and_duplicate_409(client, session):
    user, sess = await _ctx(session)
    r1 = await client.post(f"/api/tasks/from-session/{sess.id}", json={"title": "季度评审"})
    assert r1.status_code == 201
    body = r1.json()
    assert body["title"] == "季度评审" and body["kind"] == "manual" and body["status"] == "active"

    r2 = await client.post(f"/api/tasks/from-session/{sess.id}", json={"title": "再提"})
    assert r2.status_code == 409


async def test_promote_default_title_and_artifact_count(client, session):
    user, sess = await _ctx(session, "task2@test.dev")
    session.add(Artifact(user_id=user.id, session_id=sess.id, kind="image", title="x", path="/uploads/x.png"))
    await session.commit()
    r = await client.post(f"/api/tasks/from-session/{sess.id}", json=None)
    assert r.status_code == 201
    assert r.json()["title"] == "评审会话"  # 会话标题默认
    assert r.json()["artifact_count"] == 1  # 交付物归集(M25 数据天然关联)


async def test_status_flow_and_delete_not_cascade(client, session):
    user, sess = await _ctx(session, "task3@test.dev")
    created = (await client.post(f"/api/tasks/from-session/{sess.id}", json={"title": "T"})).json()

    done = await client.patch(f"/api/tasks/{created['id']}", json={"status": "done"})
    assert done.status_code == 200 and done.json()["completed_at"] is not None
    # done 不在默认(active)列表
    active_list = await client.get("/api/tasks")
    assert all(t["id"] != created["id"] for t in active_list.json())
    done_list = await client.get("/api/tasks?status=done")
    assert any(t["id"] == created["id"] for t in done_list.json())

    # DELETE 实体后会话仍在
    dele = await client.delete(f"/api/tasks/{created['id']}")
    assert dele.status_code == 204
    assert await session.get(ChatSession, sess.id) is not None


async def test_scheduler_linkage(client, session):
    """建定时任务 → 实体存在;删定时任务 → 实体转 done。"""
    user, sess = await _ctx(session, "task4@test.dev")
    sched = await create_scheduled(
        session,
        str(user.id),
        name="周报任务", kind="custom", prompt="汇总本周", schedule_type="daily", daily_at="08:00",
    )
    await session.commit()
    from sqlalchemy import select

    entity = (
        await session.scalars(
            select(TaskEntity).where(TaskEntity.scheduled_task_id == sched.id)
        )
    ).first()
    assert entity is not None and entity.kind == "scheduled" and entity.status == "active"

    ok = await delete_scheduled(session, str(user.id), sched.id)
    assert ok
    await session.commit()
    await session.refresh(entity)
    assert entity.status == "done" and entity.completed_at is not None


async def test_panel_includes_entity_section(client, session):
    user, sess = await _ctx(session, "task5@test.dev")
    session.add(Artifact(user_id=user.id, session_id=sess.id, kind="report", title="r"))
    await session.commit()
    promote = await client.post(f"/api/tasks/from-session/{sess.id}", json={"title": "面板任务"})
    assert promote.status_code == 201, promote.text

    panel = await client.get("/api/workbench/tasks")
    assert panel.status_code == 200
    tasks = panel.json()["tasks"]
    match = [t for t in tasks if t["title"] == "面板任务"]
    assert len(match) == 1 and match[0]["artifact_count"] == 1


async def test_isolation_404(client, session):
    """他人任务/会话不可见(404)。"""
    user, sess = await _ctx(session, "task6@test.dev")
    other = await create_user(session, "other@test.dev", "password123")
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: other
    r = await client.post(f"/api/tasks/from-session/{sess.id}", json={"title": "偷提"})
    assert r.status_code == 404
    r2 = await client.delete(f"/api/tasks/{uuid.uuid4()}")
    assert r2.status_code == 404


# ── M30:推送目标/测试/feishu_chat_id 透传 ────────────────────


async def test_push_targets_lists_feishu_chats(client, session):
    from agentplatform.core.channel.model import ChannelSession
    from agentplatform.core.session.model import Session as ChatSession

    user, sess = await _ctx(session, "push1@test.dev")
    session.add(ChannelSession(channel="feishu", chat_id="oc_test123", session_id=sess.id))
    await session.commit()

    r = await client.get("/api/scheduler/push-targets")
    assert r.status_code == 200
    body = r.json()
    ids = [c["chat_id"] for c in body["feishu_chats"]]
    assert "oc_test123" in ids
    label = next(c["label"] for c in body["feishu_chats"] if c["chat_id"] == "oc_test123")
    assert "评审会话" in label
    assert "smtp_configured" in body


async def test_push_test_rate_limited(client, session, monkeypatch):
    from agentplatform.api import scheduler as sched_api

    calls = []

    async def fake_push(chat_id, title, text):
        calls.append(chat_id)
        return True

    monkeypatch.setattr("agentplatform.core.channel.feishu.push_to_chat", fake_push)
    await _ctx(session, "push2@test.dev")

    r1 = await client.post("/api/scheduler/push-test", json={"chat_id": "oc_x"})
    assert r1.status_code == 200 and r1.json()["ok"] is True
    r2 = await client.post("/api/scheduler/push-test", json={"chat_id": "oc_x"})
    assert r2.status_code == 429


async def test_task_create_carries_feishu_chat_id(client, session):
    from agentplatform.core.scheduler.model import ScheduledTask
    from sqlalchemy import select

    user, _ = await _ctx(session, "push3@test.dev")
    r = await client.post(
        "/api/scheduler/tasks",
        json={
            "name": "推送任务", "kind": "custom", "prompt": "x",
            "schedule_type": "daily", "daily_at": "09:00",
            "feishu_chat_id": "oc_target",
        },
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["feishu_chat_id"] == "oc_target"
    row = (await session.scalars(select(ScheduledTask).where(ScheduledTask.name == "推送任务"))).first()
    assert row.feishu_chat_id == "oc_target"


async def test_panel_includes_done_tasks(client, session):
    """删除定时任务 → 实体转 done → 面板 done_tasks 折叠区可见(不消失)。"""
    user, sess = await _ctx(session, "done1@test.dev")
    sched = await create_scheduled(
        session, str(user.id),
        name="将删除的任务", kind="custom", prompt="x", schedule_type="daily", daily_at="07:00",
    )
    await session.commit()
    panel1 = (await client.get("/api/workbench/tasks")).json()
    assert any(t["title"] == "将删除的任务" for t in panel1["tasks"])

    ok = await delete_scheduled(session, str(user.id), sched.id)
    assert ok
    await session.commit()

    panel2 = (await client.get("/api/workbench/tasks")).json()
    assert not any(t["title"] == "将删除的任务" for t in panel2["tasks"])  # active 区移除
    assert any(t["title"] == "将删除的任务" for t in panel2["done_tasks"])  # 折叠区保留


async def test_panel_scheduled_entity_has_latest_session(client, session):
    """定时任务实体带最近执行会话(点开看执行情况);跑过一次后非空。"""
    user, _ = await _ctx(session, "latest1@test.dev")
    sched = await create_scheduled(
        session, str(user.id),
        name="看执行任务", kind="custom", prompt="x", schedule_type="daily", daily_at="06:00",
    )
    await session.commit()
    # 造一次成功运行(含会话)
    from agentplatform.core.session.model import Session as ChatSession
    from agentplatform.core.scheduler.model import TaskRun

    run_sess = ChatSession(user_id=str(user.id), title="执行现场")
    session.add(run_sess)
    await session.flush()
    session.add(TaskRun(task_id=sched.id, status="success", session_id=run_sess.id, output="ok"))
    await session.commit()

    panel = (await client.get("/api/workbench/tasks")).json()
    item = next(t for t in panel["tasks"] if t["title"] == "看执行任务")
    assert item["scheduled_task_id"] == str(sched.id)
    assert item["latest_session_id"] == str(run_sess.id)
