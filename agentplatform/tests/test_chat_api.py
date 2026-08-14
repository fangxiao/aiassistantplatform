"""对话 API 测试(设计 005 §4):会话创建、SSE 流、历史落库。

make_llm_client 注入脚本化 FakeClient,不发起真实 LLM 请求。
"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.chat.service import resource_ids_from_plugin
from agentplatform.core.llm.client import StreamEvent, ToolCall
from agentplatform.core.plugin.loader import deploy_plugin
from agentplatform.core.plugin.manifest import PluginManifest
from agentplatform.core.plugin.model import Plugin
from agentplatform.core.registry.model import SkillToolKind as K
from agentplatform.core.registry.model import SkillToolSource as S
from agentplatform.core.registry.service import register

FIXTURE_TOOL = "agentplatform.tests.fixtures.impl_tool"


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


async def _register_echo(session: AsyncSession) -> None:
    await register(
        session,
        resource_id="tool:echo",
        kind=K.tool,
        name="echo",
        version="1.0.0",
        source=S.builtin,
        schema_={"parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
        impl_path=FIXTURE_TOOL,
        description="回显 tool",
    )
    await session.commit()


async def _deploy_plugin(session: AsyncSession) -> None:
    manifest = PluginManifest(
        name="echo-assistant",
        version="0.1.0",
        description="echo 助手",
        model="deepseek-v4-flash",
        depends_on=["tool:echo@^1.0"],
        skills=[],
        tools=[],
    )
    await deploy_plugin(session, manifest)
    await session.commit()


class TestSessions:
    async def test_create_and_list(self, client: AsyncClient) -> None:
        resp = await client.post("/api/chat/sessions", json={"plugin_id": None})
        assert resp.status_code == 201
        sid = resp.json()["id"]
        resp2 = await client.get("/api/chat/sessions")
        assert [s["id"] for s in resp2.json()] == [sid]


class TestSendMessageSSE:
    async def test_plain_text_stream(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
        sid = (await client.post("/api/chat/sessions", json={"plugin_id": None})).json()["id"]
        fake = FakeClient([
            [StreamEvent(type="delta", text="你好"), StreamEvent(type="delta", text="世界"), StreamEvent(type="done", message_id="m1")],
        ])

        async def _fake_make(session_: AsyncSession, model: str | None):
            return fake

        monkeypatch.setattr("agentplatform.core.chat.service.make_llm_client", _fake_make)
        resp = await client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "嗨"})
        assert resp.status_code == 200
        frames = parse_sse(resp.text)
        events = [e for e, _ in frames]
        assert events == ["delta", "delta", "done"]
        assert frames[0][1]["text"] == "你好"
        assert frames[-1][1]["message_id"]

        # 历史落库:user + assistant
        hist = await client.get(f"/api/chat/sessions/{sid}/messages")
        roles = [m["role"] for m in hist.json()]
        assert roles == ["user", "assistant"]
        assert hist.json()[1]["text"] == "你好世界"

    async def test_tool_call_and_backfill(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch, session: AsyncSession) -> None:
        await _register_echo(session)
        await _deploy_plugin(session)
        plugin = (await client.get("/api/plugins")).json()[0]
        sid = (await client.post("/api/chat/sessions", json={"plugin_id": plugin["id"]})).json()["id"]

        fake = FakeClient([
            [StreamEvent(type="tool_call", tool_call=ToolCall(id="c1", name="tool:echo", arguments='{"text": "hi"}')), StreamEvent(type="done", message_id="m1")],
            [StreamEvent(type="delta", text="完成"), StreamEvent(type="done", message_id="m2")],
        ])

        async def _fake_make(session_: AsyncSession, model: str | None):
            return fake

        monkeypatch.setattr("agentplatform.core.chat.service.make_llm_client", _fake_make)
        resp = await client.post(f"/api/chat/sessions/{sid}/messages", json={"content": "回显 hi"})
        frames = parse_sse(resp.text)
        events = [e for e, _ in frames]
        assert "tool_call" in events
        tc = next(data for e, data in frames if e == "tool_call")
        assert tc["name"] == "tool:echo"
        assert tc["result"] == "HI"
        assert "delta" in events and "done" in events

    async def test_missing_session_404(self, client: AsyncClient) -> None:
        resp = await client.post("/api/chat/sessions/00000000-0000-0000-0000-000000000000/messages", json={"content": "x"})
        assert resp.status_code == 404


class TestResourceIds:
    async def test_from_plugin(self, session: AsyncSession) -> None:
        await _register_echo(session)
        await _deploy_plugin(session)
        plugin = (await session.scalars(select(Plugin))).first()
        assert plugin is not None
        assert resource_ids_from_plugin(plugin) == ["tool:echo"]
