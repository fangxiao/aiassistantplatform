"""草稿检查点与断点续跑测试(设计 016 §2 / ADR 0009 / P1)。

直接以假 agent 事件流驱动 _checkpointed_agent_sse,不依赖 LLM:
- 正常完成:草稿 finalize 转正式,done 携带 message_id 与 tokens
- 流中途异常:partial 留草稿(is_draft 保持),error 事件带 resumable
- resume:latest_draft 定位 → 续跑产物原地并入草稿 finalize
- 工具边界:flush 先于 yield,客户端恰在该点断开时检查点已落库
"""

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.api.chat import _checkpointed_agent_sse
from agentplatform.core.agent.loop import AgentEvent
from agentplatform.core.message.model import MessageRole
from agentplatform.core.message.service import (
    latest_draft_message,
    list_messages,
    save_user_message,
)
from agentplatform.core.session.service import create_session


def _parse(frames: list[str]) -> list[tuple[str, dict]]:
    out = []
    for f in frames:
        lines = f.strip().split("\n")
        out.append((lines[0][len("event: "):], json.loads(lines[1][len("data: "):])))
    return out


async def _collect(agen) -> list[str]:
    return [chunk async for chunk in agen]


def _events(*specs: tuple) -> AsyncIterator[AgentEvent]:
    async def gen():
        for spec in specs:
            if spec[0] == "raise":
                raise spec[1]
            yield AgentEvent(
                type=spec[0],
                text=spec[1] if len(spec) > 1 else None,
                usage=spec[2] if len(spec) > 2 else None,
            )

    return gen()


@pytest.mark.asyncio
async def test_normal_stream_finalizes_draft(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="ckpt")
    await session.commit()

    frames = await _collect(_checkpointed_agent_sse(
        session, s.id,
        _events(("delta", "你好"), ("delta", "世界"), ("done", None, {"total_tokens": 42})),
    ))
    parsed = _parse(frames)
    done_payload = [d for k, d in parsed if k == "done"][0]
    assert done_payload["tokens"] == 42
    assert done_payload["message_id"]

    msgs = await list_messages(session, s.id)
    assistant = [m for m in msgs if m.role == MessageRole.assistant]
    assert len(assistant) == 1
    assert assistant[0].is_draft is False  # finalize 转正式
    assert "你好世界" in assistant[0].blocks[0]["data"]["text"]
    assert assistant[0].tokens == 42


@pytest.mark.asyncio
async def test_stream_error_keeps_draft_and_reports_resumable(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="ckpt-err")
    await session.commit()

    class Boom(RuntimeError):
        pass

    frames = await _collect(_checkpointed_agent_sse(
        session, s.id, _events(("delta", "部分产出"), ("raise", Boom("上游断流"))),
    ))
    parsed = _parse(frames)
    errors = [d for k, d in parsed if k == "error"]
    assert errors and errors[0]["resumable"] is True
    assert errors[0]["message_id"]

    # 检查点留存:partial 在草稿行中,is_draft 保持 True
    draft = await latest_draft_message(session, s.id)
    assert draft is not None
    assert draft.id == uuid.UUID(errors[0]["message_id"])
    assert "部分产出" in draft.blocks[0]["data"]["text"]
    assert draft.is_draft is True


@pytest.mark.asyncio
async def test_resume_appends_to_draft_and_finalizes(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="ckpt-resume")
    await save_user_message(session, s.id, "写首诗")
    await session.commit()

    class Boom(RuntimeError):
        pass

    # 第一次:中断留草稿
    await _collect(_checkpointed_agent_sse(
        session, s.id, _events(("delta", "春风拂柳"), ("raise", Boom("断"))),
    ))
    draft = await latest_draft_message(session, s.id)
    assert draft is not None and draft.is_draft is True

    # resume:续跑产物原地并入并 finalize
    frames = await _collect(_checkpointed_agent_sse(
        session, s.id,
        _events(("delta", ",万里无云"), ("done", None, {"total_tokens": 10})),
        draft=draft, is_resume=True,
    ))
    parsed = _parse(frames)
    assert [d for k, d in parsed if k == "resume_started"][0]["message_id"] == str(draft.id)
    assert [d for k, d in parsed if k == "done"][0]["resume_of"] == str(draft.id)

    msgs = await list_messages(session, s.id)
    assistant = [m for m in msgs if m.role == MessageRole.assistant]
    assert len(assistant) == 1  # 原地并入,不产生第二条
    text = "".join(
        b.get("data", {}).get("text", "") for b in assistant[0].blocks or []
        if isinstance(b, dict) and b.get("type") == "markdown"
    )
    assert "春风拂柳" in text and "万里无云" in text  # 旧部分+续跑产物均在
    assert assistant[0].is_draft is False


@pytest.mark.asyncio
async def test_generator_exit_spawns_tail_persist(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """客户端断开(GeneratorExit):尾部经独立任务落盘,partial 转正式。"""
    import asyncio as _asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from agentplatform.core.db import session as db_session_mod

    # 独立任务用 SessionLocal 开新会话——重定向到测试引擎
    monkeypatch.setattr(
        db_session_mod,
        "SessionLocal",
        async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False),
    )

    s = await create_session(session, plugin_id=None, title="ckpt-gexit")
    await session.commit()

    async def gen() -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type="delta", text="断开前的尾部内容")
        yield AgentEvent(type="done", usage={"total_tokens": 3})

    agen = _checkpointed_agent_sse(session, s.id, gen())
    async for chunk in agen:
        if chunk.startswith("event: delta"):
            break
    await agen.aclose()  # 模拟客户端断开触发的生成器关闭

    # 等待派生的独立落盘任务完成
    pending = [t for t in _asyncio.all_tasks() if t is not _asyncio.current_task()]
    await _asyncio.gather(*pending, return_exceptions=True)

    draft = await latest_draft_message(session, s.id)
    assert draft is None  # partial 已转正式,不再是草稿
    msgs = await list_messages(session, s.id)
    assistant = [m for m in msgs if m.role == MessageRole.assistant]
    assert len(assistant) == 1
    assert "断开前的尾部内容" in json.dumps(assistant[0].blocks, ensure_ascii=False)


@pytest.mark.asyncio
async def test_tool_call_boundary_flush_survives_disconnect(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="ckpt-tool")
    await session.commit()

    class _T:
        id = "tool:demo"

    async def gen() -> AsyncIterator[AgentEvent]:
        yield AgentEvent(type="delta", text="调用前文本")
        yield AgentEvent(type="tool_call", tool_trace=_T())
        yield AgentEvent(type="delta", text="这段不应出现在检查点")
        yield AgentEvent(type="done", usage={"total_tokens": 5})

    # 消费到 tool_call 事件即停止(模拟客户端恰在该点断开)
    agen = _checkpointed_agent_sse(session, s.id, gen())
    async for chunk in agen:
        if chunk.startswith("event: tool_call"):
            break
    await agen.aclose()

    draft = await latest_draft_message(session, s.id)
    assert draft is not None
    # flush 先于 yield:调用前文本已落检查点,后续文本未进入
    assert "调用前文本" in json.dumps(draft.blocks, ensure_ascii=False)
    assert "这段不应出现" not in json.dumps(draft.blocks, ensure_ascii=False)
