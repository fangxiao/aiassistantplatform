"""M25 任务面板与交付物测试(需求 014/设计 019)。

覆盖:登记服务(白名单/URL 提取/自愈)、聚合端点(三栏/隔离/现签/report 内容)。
loop 埋点与 scheduler 登记走线上冒烟(设计 019 §6)。
"""

import uuid

from sqlalchemy import select

from agentplatform.core.artifacts.model import Artifact
from agentplatform.core.artifacts.service import (
    extract_file_path,
    register_task_report,
    register_tool_artifact,
)
from agentplatform.core.auth.service import create_user
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun

PREFIX = "/api/workbench/tasks"


async def _make_user(session, email: str):
    user = await create_user(session, email, "password123")
    await session.commit()
    return user


# ── 登记服务 ──────────────────────────────────────────────────


async def test_register_tool_artifact_extracts_path(session):
    user = await _make_user(session, "art1@test.dev")
    result = '图片已生成: /api/files/raw?path=%2Fuploads%2Fab.png&exp=123&sig=deadbeef'
    await register_tool_artifact(
        session,
        tool_id="tool:image_gen",
        result=result,
        args={"prompt": "一只柴犬 水彩"},
        owner_id=str(user.id),
        chat_session_id=None,
    )
    rows = (await session.scalars(select(Artifact))).all()
    assert len(rows) == 1
    assert rows[0].kind == "image"
    assert rows[0].path == "/uploads/ab.png"
    assert rows[0].title == "一只柴犬 水彩"
    assert rows[0].session_id is None


async def test_register_tool_artifact_whitelist_only(session):
    user = await _make_user(session, "art2@test.dev")
    await register_tool_artifact(
        session,
        tool_id="tool:pdf_parse",  # 非白名单
        result="/api/files/raw?path=%2Fx&exp=1&sig=s",
        args={},
        owner_id=str(user.id),
        chat_session_id=None,
    )
    assert (await session.scalars(select(Artifact))).all() == []


async def test_register_tool_artifact_self_healing(session):
    """异常(如 owner_id 非法)不外抛——闭环自愈(需求 A2)。"""
    await register_tool_artifact(
        session,
        tool_id="tool:image_gen",
        result="/api/files/raw?path=%2Fa&exp=1&sig=s",
        args={"prompt": "x"},
        owner_id="not-a-uuid",
        chat_session_id=None,
    )


async def test_register_task_report(session):
    user = await _make_user(session, "art3@test.dev")
    sid = uuid.uuid4()
    rid = uuid.uuid4()
    await register_task_report(
        session,
        owner_id=str(user.id),
        title="每日简报 · 10-06",
        chat_session_id=str(sid),
        task_run_id=str(rid),
    )
    row = (await session.scalars(select(Artifact))).first()
    assert row is not None
    assert row.kind == "report"
    assert row.session_id == sid and row.task_run_id == rid
    assert row.path is None


async def test_derive_title_html_strips_tags():
    from agentplatform.core.artifacts.service import derive_title

    title = derive_title("tool:html_render", {"html": "<h1>季度 评审 报告</h1><p>x</p>"})
    assert title == "季度 评审 报告 x"
    assert derive_title("tool:image_gen", {"prompt": "p" * 100}) == "p" * 40
    assert derive_title("tool:html_render", {"html": "<div></div>"}) == "html_render"


async def test_extract_file_path():
    assert extract_file_path("/api/files/raw?path=%2Fuploads%2Fa.png&exp=1&sig=s") == "/uploads/a.png"
    assert extract_file_path("https://x.dev/api/files/raw?path=%2Fb&exp=1&sig=s") == "/b"
    assert extract_file_path("https://x.dev/other") is None


# ── 聚合端点 ──────────────────────────────────────────────────


async def _seed_panel_data(session, user):
    """造:1 活跃会话 + 1 running run + 2 任务 + 2 交付物(文件/report)。"""
    from datetime import UTC, datetime, timedelta

    from agentplatform.core.message.model import Message, MessageRole
    from agentplatform.core.session.model import Session as ChatSession

    sess = ChatSession(user_id=str(user.id), title="评审会话", updated_at=datetime.now(UTC))
    session.add(sess)
    await session.flush()
    session.add(
        Message(
            session_id=sess.id,
            role=MessageRole.assistant,
            blocks=[{"type": "text", "text": "评审完成,结论如下"}],
        )
    )
    task = ScheduledTask(
        user_id=str(user.id), name="每日简报", kind="briefing",
        next_run_at=datetime.now(UTC) + timedelta(hours=8), last_status="success",
    )
    session.add(task)
    await session.flush()
    run = TaskRun(task_id=task.id, status="running", session_id=sess.id)
    session.add(run)
    await session.flush()
    session.add(
        Artifact(
            user_id=user.id, session_id=sess.id, kind="image",
            title="柴犬水彩", path="/uploads/doge.png",
        )
    )
    report_run = TaskRun(task_id=task.id, status="success", output="今日 3 条动态,1 条待办")
    session.add(report_run)
    await session.flush()
    session.add(
        Artifact(
            user_id=user.id, session_id=sess.id, task_run_id=report_run.id,
            kind="report", title="每日简报 · 10-06",
        )
    )
    await session.commit()
    return sess, task


async def test_tasks_panel_aggregates_three_sections(client, session):
    # client fixture 的鉴权用户(dependency override 返回的 admin)——种子必须挂它名下
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    user = app.dependency_overrides[get_current_user]()
    _sess, _task = await _seed_panel_data(session, user)

    resp = await client.get(PREFIX)
    assert resp.status_code == 200
    body = resp.json()

    # 进行中:活跃会话 + running run
    titles = {r["title"] for r in body["running"]}
    assert "评审会话" in titles and "每日简报" in titles
    sess_item = next(r for r in body["running"] if r["kind"] == "session")
    assert "评审完成" in sess_item["detail"]

    # 定时任务
    assert body["scheduled"][0]["name"] == "每日简报"
    assert body["scheduled"][0]["last_status"] == "success"

    # 交付物:image 带现签 URL;report 带 content 无 URL
    image_item = next(a for a in body["artifacts"] if a["kind"] == "image")
    assert image_item["signed_url"] and "/api/files/raw" in image_item["signed_url"]
    report_item = next(a for a in body["artifacts"] if a["kind"] == "report")
    assert report_item["signed_url"] is None
    assert "动态" in (report_item["content"] or "")


async def test_tasks_panel_user_isolation(client, session):
    """种子数据属于另一用户;client fixture 的鉴权用户查不到(user_id 过滤,A4)。"""
    user = await _make_user(session, "panel2@test.dev")
    await _seed_panel_data(session, user)

    resp = await client.get(PREFIX)
    assert resp.status_code == 200
    body = resp.json()
    assert body["artifacts"] == []
    assert body["scheduled"] == []
    assert body["running"] == []
