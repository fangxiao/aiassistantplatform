"""上下文压缩测试(M21 P3 / 需求 011 H3 / ADR 0011):验收 A3 用例集。

不依赖真实 LLM:摘要调用以假 client(stream 接口)替换。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.context import (
    estimate_tokens,
    maybe_compact_history,
)
from agentplatform.core.message.model import MessageRole
from agentplatform.core.message.service import (
    build_history,
    save_assistant_message,
    save_user_message,
)
from agentplatform.core.session.service import create_session


class _FakeSummaryClient:
    """stream 接口假实现:固定返回摘要文本。"""

    supports_native_tools = False

    def __init__(self, text: str = "摘要:用户目标=两个月英语;偏好=早上学习。"):
        self._text = text
        self.calls: list[str] = []

    async def stream(self, messages, tools=None):
        self.calls.append(messages[0]["content"])
        yield type("E", (), {"type": "delta", "text": self._text})()


def _big_history(n: int = 40, size: int = 400) -> list[dict]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": "字" * size}
        for i in range(n)
    ]


@pytest.fixture(autouse=True)
def _small_threshold(monkeypatch):
    """测试用小阈值:40×400字 ≈ 6400 tokens,阈值降到 1000 确保触发。"""
    from agentplatform.config import settings

    monkeypatch.setattr(settings, "context_compact_max_tokens", 1000)
    monkeypatch.setattr(settings, "context_compact_keep_recent", 12)


def test_estimate_tokens_monotonic() -> None:
    assert estimate_tokens(_big_history(2)) < estimate_tokens(_big_history(10))


@pytest.mark.asyncio
async def test_compact_triggers_writes_summary_and_keeps_recent(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="compact")
    await session.commit()
    client = _FakeSummaryClient()
    history = _big_history()

    out = await maybe_compact_history(session, s.id, history, client)

    assert len(client.calls) == 1  # 触发一次摘要
    assert len(out) == 13  # 1 条注入摘要 + keep_recent(12)
    assert out[0]["content"].startswith("(系统注入")
    assert "英语" in out[0]["content"]  # 摘要内容注入
    # summary 行已固化
    await session.commit()
    rows = [
        m
        for m in await __import__("agentplatform.core.message.service", fromlist=["list_messages"]).list_messages(
            session, s.id
        )
        if m.role == MessageRole.summary
    ]
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_compact_cooldown_gate(session: AsyncSession) -> None:
    """频率闸:触发一次后立刻再触发,不重复摘要。"""
    s = await create_session(session, plugin_id=None, title="gate")
    await session.commit()
    client = _FakeSummaryClient()
    await maybe_compact_history(session, s.id, _big_history(), client)
    out2 = await maybe_compact_history(session, s.id, _big_history(), client)
    assert len(client.calls) == 1  # 冷却期内不再调用
    assert len(out2) == 40  # 原样返回


@pytest.mark.asyncio
async def test_build_history_uses_summary_as_baseline(session: AsyncSession) -> None:
    """压缩后历史以 summary 为基线:只取其后消息,不再回涨。"""
    s = await create_session(session, plugin_id=None, title="baseline")
    # 早期消息(将被摘要覆盖)
    for i in range(10):
        await save_user_message(session, s.id, f"早期{i} " + "字" * 300)
        await save_assistant_message(session, s.id, f"答{i} " + "字" * 300)
    client = _FakeSummaryClient()
    await maybe_compact_history(session, s.id, await build_history(session, s.id), client)
    await session.commit()
    # 摘要之后的正常轮次
    await save_user_message(session, s.id, "摘要后的新问题")
    await save_assistant_message(session, s.id, "新回答")
    await session.commit()

    history = await build_history(session, s.id)
    assert history[0]["content"].startswith("(系统注入")
    joined = "".join(m["content"] for m in history)
    assert "早期0" not in joined  # 被摘要覆盖的原文不再进历史
    assert "摘要后的新问题" in joined


@pytest.mark.asyncio
async def test_summary_prompt_preserves_constraints(session: AsyncSession) -> None:
    """验收 A3:摘要 prompt 明确要求逐条保留用户约束与偏好。"""
    s = await create_session(session, plugin_id=None, title="prompt")
    await session.commit()
    client = _FakeSummaryClient()
    await maybe_compact_history(session, s.id, _big_history(), client)
    assert "逐条保留" in client.calls[0]
    assert "约束" in client.calls[0]
