"""agent 调度循环测试:显式调用编排、执行回填、skill 嵌套调用、错误处理。

llm_client 用脚本化 FakeClient 完全 mock,不发起真实 LLM 请求。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.errors import AgentLoopError
from agentplatform.core.agent.loop import run_agent
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
        _, tools = fake.calls[0]
        assert tools is not None
        assert any(t["function"]["name"] == "tool:echo" for t in tools)
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
