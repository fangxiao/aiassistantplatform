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
