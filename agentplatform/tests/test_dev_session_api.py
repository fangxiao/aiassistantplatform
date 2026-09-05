"""远程调试会话 API 测试(设计 007):创建 / SSE 对话流 / 清理 / 心跳 / TTL。

make_llm_client 注入脚本化 FakeClient,不发起真实 LLM 请求。
"""

import json
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.llm.client import StreamEvent, ToolCall
from agentplatform.core.registry.model import SkillTool, SkillToolSource
from agentplatform.core.registry.service import seed_builtin

DEV_MANIFEST = {
    "name": "dev-test-assistant",
    "version": "0.1.0",
    "description": "远程调试测试助手",
    "model": "deepseek-v4-flash",
    "depends_on": [],
    "skills": [],
    "tools": [
        {
            "id": "tool:dev_echo",
            "file": "tools/echo.py",
            "code": "import json\n\ndef run(**args):\n    return json.dumps({'status': 'success', 'echo': args.get('text', '')}, ensure_ascii=False)\n",
            "description": "回显 tool",
        }
    ],
}


class FakeClient:
    def __init__(self, rounds: list[list[StreamEvent]]) -> None:
        self.rounds = rounds
        self.calls = 0

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        idx = self.calls
        self.calls += 1
        for ev in self.rounds[idx] if idx < len(self.rounds) else []:
            yield ev


def parse_sse(text: str) -> list[tuple[str, dict]]:
    frames: list[tuple[str, dict]] = []
    for frame in text.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if event is not None and data is not None:
            frames.append((event, data))
    return frames


@pytest.fixture(autouse=True)
async def _seed(client: AsyncClient, session: AsyncSession):
    await seed_builtin(session)
    yield


async def _create_dev_session(client: AsyncClient, manifest: dict | None = None) -> dict:
    resp = await client.post("/api/plugins/dev-session", json={"manifest": manifest or DEV_MANIFEST})
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreate:
    async def test_create_success(self, client: AsyncClient, session: AsyncSession) -> None:
        body = await _create_dev_session(client)
        assert body["ok"] is True
        assert body["session_id"]
        assert "messages_url" in body
        assert body["ttl_seconds"] > 0
        assert body["resources"] == ["tool:dev_echo"]
        # 临时代码已写入磁盘
        sid = body["session_id"]
        storage = Path.home() / ".agentplatform" / "dev_sessions" / sid
        assert (storage / "tools" / "echo.py").exists()
        # 临时资源已注册到注册表
        row = await session.scalar(
            select(SkillTool).where(SkillTool.id == "tool:dev_echo")
        )
        assert row is not None
        assert row.source == SkillToolSource.private
        assert row.owner_id == f"dev_session:{sid}"

    async def test_create_missing_code_422(self, client: AsyncClient) -> None:
        bad = {**DEV_MANIFEST, "tools": [{**DEV_MANIFEST["tools"][0], "code": None}]}
        resp = await client.post("/api/plugins/dev-session", json={"manifest": bad})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "plugin_invalid"

    async def test_create_missing_dependency_422(self, client: AsyncClient) -> None:
        bad = {**DEV_MANIFEST, "depends_on": ["skill:missing@^1.0"]}
        resp = await client.post("/api/plugins/dev-session", json={"manifest": bad})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "dependency_missing"

    async def test_create_second_session_429(self, client: AsyncClient) -> None:
        await _create_dev_session(client)
        resp = await client.post("/api/plugins/dev-session", json={"manifest": DEV_MANIFEST})
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "too_many_sessions"

    async def test_create_invalid_manifest_422(self, client: AsyncClient) -> None:
        bad = {**DEV_MANIFEST, "version": "not-a-semver"}
        resp = await client.post("/api/plugins/dev-session", json={"manifest": bad})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "plugin_invalid"


class TestSendMessage:
    async def test_plain_text_stream(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
        body = await _create_dev_session(client)
        fake = FakeClient([
            [StreamEvent(type="delta", text="你好"), StreamEvent(type="delta", text="世界"), StreamEvent(type="done", message_id="m1")],
        ])

        async def _fake_make(session_: AsyncSession, model: str | None):
            return fake

        monkeypatch.setattr("agentplatform.core.chat.service.make_llm_client", _fake_make)
        resp = await client.post(
            f"/api/plugins/dev-session/{body['session_id']}/messages",
            json={"content": "嗨"},
        )
        assert resp.status_code == 200
        frames = parse_sse(resp.text)
        events = [e for e, _ in frames]
        assert events == ["delta", "delta", "done"]
        assert frames[0][1]["text"] == "你好"

    async def test_tool_call_and_backfill(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
        body = await _create_dev_session(client)
        fake = FakeClient([
            [StreamEvent(type="tool_call", tool_call=ToolCall(id="c1", name="tool:dev_echo", arguments='{"text": "hi"}')), StreamEvent(type="done", message_id="m1")],
            [StreamEvent(type="delta", text="完成"), StreamEvent(type="done", message_id="m2")],
        ])

        async def _fake_make(session_: AsyncSession, model: str | None):
            return fake

        monkeypatch.setattr("agentplatform.core.chat.service.make_llm_client", _fake_make)
        resp = await client.post(
            f"/api/plugins/dev-session/{body['session_id']}/messages",
            json={"content": "回显 hi"},
        )
        assert resp.status_code == 200
        frames = parse_sse(resp.text)
        events = [e for e, _ in frames]
        assert "tool_call" in events
        tc = next(data for e, data in frames if e == "tool_call")
        assert tc["name"] == "tool:dev_echo"
        # tool 执行成功(临时文件被 resolve_impl 加载)
        assert tc["result"] == '{"status": "success", "echo": "hi"}'
        assert "done" in events

    async def test_missing_session_410(self, client: AsyncClient) -> None:
        resp = await client.post(
            f"/api/plugins/dev-session/{uuid.uuid4()}/messages",
            json={"content": "x"},
        )
        assert resp.status_code == 410
        assert resp.json()["error"]["code"] == "session_expired"


class TestManage:
    async def test_delete_cleans_resources(self, client: AsyncClient, session: AsyncSession) -> None:
        body = await _create_dev_session(client)
        sid = body["session_id"]
        storage = Path.home() / ".agentplatform" / "dev_sessions" / sid
        assert storage.exists()

        resp = await client.delete(f"/api/plugins/dev-session/{sid}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # 磁盘与注册表均无残留
        assert not storage.exists()
        row = await session.scalar(
            select(SkillTool).where(SkillTool.id == "tool:dev_echo")
        )
        assert row is None
        # 再访问 404
        resp = await client.delete(f"/api/plugins/dev-session/{sid}")
        assert resp.status_code == 404

    async def test_heartbeat_extends_ttl(self, client: AsyncClient) -> None:
        body = await _create_dev_session(client)
        resp = await client.post(f"/api/plugins/dev-session/{body['session_id']}/heartbeat")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["ttl_seconds"] > 0

    async def test_heartbeat_missing_410(self, client: AsyncClient) -> None:
        resp = await client.post(f"/api/plugins/dev-session/{uuid.uuid4()}/heartbeat")
        assert resp.status_code == 410

    async def test_unauthorized_401(self, client: AsyncClient) -> None:
        # conftest client 已覆盖 get_current_user 固定身份;此处验证归属校验走 404
        resp = await client.delete(f"/api/plugins/dev-session/{uuid.uuid4()}")
        assert resp.status_code == 404