"""agent 调度循环测试:显式调用编排、执行回填、skill 嵌套调用、错误处理。

llm_client 用脚本化 FakeClient 完全 mock,不发起真实 LLM 请求。
"""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.bridge import bridge
from agentplatform.core.agent.errors import AgentLoopError
from agentplatform.core.agent.loop import run_agent, stream_agent
from agentplatform.core.llm.client import StreamEvent, ToolCall
from agentplatform.core.registry.model import SkillToolKind as K
from agentplatform.core.registry.model import SkillToolSource as S
from agentplatform.core.registry.service import register

FIXTURE_TOOL = "agentplatform.tests.fixtures.impl_tool"
BUILTIN_SUMMARIZE = "agentplatform.core.registry.builtin.summarize"


class FakeClient:
    """脚本化 LLM 客户端:每次 stream 按序消费 rounds,耗尽后返回空。"""

    def __init__(self, rounds: list[list[StreamEvent]]) -> None:
        self.rounds = rounds
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        self.calls.append((list(messages), tools))
        idx = len(self.calls) - 1
        for ev in self.rounds[idx] if idx < len(self.rounds) else []:
            yield ev


def _call(name: str, arguments: str) -> StreamEvent:
    return StreamEvent(type="tool_call", tool_call=ToolCall(id="call_1", name=name, arguments=arguments))


def _text(text: str) -> StreamEvent:
    return StreamEvent(type="delta", text=text)


async def _register_echo(session: AsyncSession) -> None:
    await register(
        session,
        resource_id="tool:echo",
        kind=K.tool,
        name="echo",
        version="1.0.0",
        source=S.builtin,
        schema_={
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }
        },
        impl_path=FIXTURE_TOOL,
        description="回显 tool",
    )
    await session.commit()


class TestToolLoop:
    async def test_tool_call_then_answer(self, session: AsyncSession) -> None:
        await _register_echo(session)
        fake = FakeClient([
            [_call("tool:echo", '{"text": "hi"}'), StreamEvent(type="done", message_id="m1")],
            [_text("完成"), StreamEvent(type="done", message_id="m2")],
        ])
        result = await run_agent(session, fake, resource_ids=["tool:echo"], user_message="说 hi")

        assert result.text == "完成"
        assert len(result.tool_traces) == 1
        trace = result.tool_traces[0]
        assert trace.id == "tool:echo"
        assert trace.args == {"text": "hi"}
        assert trace.result == "HI"  # fixture 实现大写

        # 编排:tools 参数带 echo 的 function 定义
        # 注意:function 名经合法字符清洗,":" -> "__"(OpenAI 函数名不允许冒号)
        _, tools = fake.calls[0]
        assert tools is not None
        assert any(t["function"]["name"] == "tool__echo" for t in tools)
        # 回填:第二次调用消息含 assistant tool_calls + tool 结果

        messages = fake.calls[1][0]
        assert messages[-1] == {"role": "tool", "tool_call_id": "call_1", "content": "HI"}

    async def test_unknown_tool_call_reported(self, session: AsyncSession) -> None:
        await _register_echo(session)
        fake = FakeClient([
            [_call("tool:nope", "{}"), StreamEvent(type="done", message_id="m1")],
            [_text("ok"), StreamEvent(type="done", message_id="m2")],
        ])
        result = await run_agent(session, fake, resource_ids=["tool:echo"], user_message="x")
        assert "未找到" in result.tool_traces[0].result

    async def test_no_tool_calls_returns_text(self, session: AsyncSession) -> None:
        fake = FakeClient([[_text("直接回答"), StreamEvent(type="done", message_id="m1")]])
        result = await run_agent(session, fake, resource_ids=[], user_message="hi")
        assert result.text == "直接回答"
        assert result.tool_traces == []


class TestSkillNestedLoop:
    async def test_skill_nested_llm_call(self, session: AsyncSession) -> None:
        await register(
            session,
            resource_id="skill:summarize",
            kind=K.skill,
            name="summarize",
            version="1.0.0",
            source=S.builtin,
            schema_={"parameters": {"type": "object"}},
            impl_path=BUILTIN_SUMMARIZE,
            description="摘要",
        )
        await session.commit()
        fake = FakeClient([
            [_call("skill:summarize", '{"text": "很长内容", "style": "concise", "max_words": 50}'), StreamEvent(type="done", message_id="m1")],
            [_text("摘要结果"), StreamEvent(type="done", message_id="m2")],  # 嵌套 skill 调用
            [_text("最终回答"), StreamEvent(type="done", message_id="m3")],
        ])
        result = await run_agent(
            session, fake, resource_ids=["skill:summarize"], user_message="帮我摘要"
        )
        assert result.tool_traces[0].result == "摘要结果"
        assert result.text == "最终回答"
        assert len(fake.calls) == 3  # 主调用 + 嵌套 skill 调用 + 回填后再推理


class TestErrors:
    async def test_llm_error_raises(self, session: AsyncSession) -> None:
        fake = FakeClient([[StreamEvent(type="error", error="HTTP 500: boom")]])
        with pytest.raises(AgentLoopError, match="HTTP 500"):
            await run_agent(session, fake, resource_ids=[], user_message="hi")


async def _register_endpoint(session: AsyncSession) -> None:
    """登记一个端侧工具(impl_path 以 endpoint: 前缀标记,不本地执行)。"""
    await register(
        session,
        resource_id="tool:browser.read_page",
        kind=K.tool,
        name="read_page",
        version="1.0.0",
        source=S.builtin,
        schema_={
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
            }
        },
        impl_path="endpoint:browser.action.readPage",
        description="读取浏览器当前/指定页面",
    )
    await session.commit()


class TestEndpointTunnel:
    """端侧工具经浏览器隧道路由:已连接走桥接回填,未连接降级 await_external。"""

    async def test_routed_through_bridge_when_connected(self, session: AsyncSession) -> None:
        await _register_endpoint(session)

        sent: list[dict] = []

        async def fake_send(msg: dict) -> None:
            sent.append(msg)
            # 模拟浏览器执行完毕,同步回传结果
            bridge.deliver_result(msg["callId"], {"ok": True, "rows": [["Plus", "$10"]]})

        sess = bridge.register("user-1", fake_send)
        try:
            fake = FakeClient([
                [_call("tool:browser.read_page", '{"url": "https://x"}'), StreamEvent(type="done", message_id="m1")],
                [_text("已读取"), StreamEvent(type="done", message_id="m2")],
            ])
            result = await run_agent(
                session, fake,
                resource_ids=["tool:browser.read_page"],
                user_message="读一下",
                owner_id="user-1",
            )
        finally:
            bridge.unregister("user-1", sess)

        # 桥接路径:结果回填,loop 继续到最终文本
        assert result.text == "已读取"
        assert len(result.tool_traces) == 1
        trace = result.tool_traces[0]
        assert trace.id == "tool:browser.read_page"
        assert trace.result == '{"ok": true, "rows": [["Plus", "$10"]]}'
        # TOOL_CALL 已下发到浏览器
        assert sent and sent[0]["type"] == "TOOL_CALL"
        assert sent[0]["toolCall"]["name"] == "browser.action.readPage"

    async def test_falls_back_to_await_external_when_not_connected(self, session: AsyncSession) -> None:
        await _register_endpoint(session)
        fake = FakeClient([
            [_call("tool:browser.read_page", "{}"), StreamEvent(type="done", message_id="m1")],
        ])
        events = [
            ev
            async for ev in stream_agent(
                session, fake,
                resource_ids=["tool:browser.read_page"],
                user_message="读一下",
                owner_id="user-1",
            )
        ]
        types = [ev.type for ev in events]
        assert "await_external" in types
        # 无浏览器连接:暂停,不产出 done,不回填
        assert "done" not in types

    async def test_falls_back_without_owner(self, session: AsyncSession) -> None:
        """owner_id 为 None(旧调用/非流式聚合路径)也走 await_external 降级。"""
        await _register_endpoint(session)
        fake = FakeClient([
            [_call("tool:browser.read_page", "{}"), StreamEvent(type="done", message_id="m1")],
        ])
        events = [
            ev
            async for ev in stream_agent(
                session, fake, resource_ids=["tool:browser.read_page"], user_message="读一下"
            )
        ]
        assert "await_external" in [ev.type for ev in events]
        assert "done" not in [ev.type for ev in events]


class TestTruncationNotice:
    """20261014:末轮 finish_reason=length(max_tokens 截断)须注入可见提示。

    背景:网关此前把截断伪装成 end_turn,平台误以为模型正常答完;
    网关修复后如实回传,平台侧负责把截断显性化给用户。
    """

    async def test_length_finish_reason_appends_notice(self, session: AsyncSession) -> None:
        fake = FakeClient([
            [
                _text("下面是流程耗时与关键指标的详细分"),
                StreamEvent(type="done", message_id="m1", finish_reason="length"),
            ],
        ])
        result = await run_agent(session, fake, resource_ids=[], user_message="做分析")
        assert result.text.startswith("下面是流程耗时")
        assert "截断" in result.text

    async def test_max_tokens_finish_reason_also_triggers(self, session: AsyncSession) -> None:
        """Anthropic 风格的 max_tokens 映射值同样判定为截断。"""
        fake = FakeClient([
            [_text("写到一半"), StreamEvent(type="done", message_id="m1", finish_reason="max_tokens")],
        ])
        result = await run_agent(session, fake, resource_ids=[], user_message="问")
        assert "截断" in result.text

    async def test_normal_stop_no_notice(self, session: AsyncSession) -> None:
        fake = FakeClient([
            [_text("完整回答"), StreamEvent(type="done", message_id="m1", finish_reason="stop")],
        ])
        result = await run_agent(session, fake, resource_ids=[], user_message="问")
        assert result.text == "完整回答"

    async def test_stream_events_expose_truncated_flag(self, session: AsyncSession) -> None:
        fake = FakeClient([
            [_text("截断内容"), StreamEvent(type="done", message_id="m1", finish_reason="length")],
        ])
        events = [ev async for ev in stream_agent(session, fake, resource_ids=[], user_message="问")]
        done = next(ev for ev in events if ev.type == "done")
        assert done.truncated is True
        assert any(ev.type == "delta" and "截断" in (ev.text or "") for ev in events)


class TestRoundEndText:
    """20261014 工单:round_end 携带本轮文本,供 SSE 消费方做工具轮过渡语治理。

    语义与 M34 一致:round_end 仅工具轮发出(末轮经 break 退出,无 round_end)。
    """

    async def test_tool_round_carries_text(self, session: AsyncSession) -> None:
        await _register_echo(session)
        fake = FakeClient([
            [
                _text("让我调用工具处理"),
                _call("tool:echo", '{"text": "hi"}'),
                StreamEvent(type="done", message_id="m1"),
            ],
            [_text("完成"), StreamEvent(type="done", message_id="m2")],
        ])
        events = [
            ev
            async for ev in stream_agent(
                session, fake, resource_ids=["tool:echo"], user_message="hi"
            )
        ]
        round_ends = [ev for ev in events if ev.type == "round_end"]
        assert len(round_ends) == 1
        assert round_ends[0].had_tool_calls is True
        assert round_ends[0].text == "让我调用工具处理"


class TestToolContextImages:
    """20261014:工具 ctx 透传本轮图片 URL(错题带图录入等场景)。"""

    async def test_tool_ctx_carries_images(self, session: AsyncSession) -> None:
        await register(
            session,
            resource_id="tool:ctx_capture",
            kind=K.tool,
            name="ctx_capture",
            version="1.0.0",
            source=S.builtin,
            schema_={"parameters": {"type": "object", "properties": {}}},
            impl_path="agentplatform.tests.fixtures.ctx_capture",
            description="回显 ctx",
        )
        await session.commit()
        fake = FakeClient([
            [
                _call("tool:ctx_capture", "{}"),
                StreamEvent(type="done", message_id="m1", finish_reason="tool_calls"),
            ],
            [_text("已附题图"), StreamEvent(type="done", message_id="m2")],
        ])
        result = await run_agent(
            session,
            fake,
            resource_ids=["tool:ctx_capture"],
            user_message="录入这道题",
            images=["https://ai-api.example.com/api/files/raw?path=/x.png&sig=y"],
        )
        ctx_echo = json.loads(result.tool_traces[0].result)
        assert ctx_echo["images"] == ["https://ai-api.example.com/api/files/raw?path=/x.png&sig=y"]
