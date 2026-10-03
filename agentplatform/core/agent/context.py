"""上下文压缩(M21 P3 / 需求 011 H3 / ADR 0011):单滚动摘要 + 增量维护。

策略:历史估算超过阈值时,保留最近 keep_recent 条原文,更早部分与旧摘要
合并为一条新摘要(一次低温 LLM 调用),以 MessageRole.summary 行固化——
同会话仅一条摘要行,原地滚动更新;10 分钟频率闸防反复触发。

摘要 prompt 固定要求"用户声明的约束与偏好逐条保留"(验收 A3 用例集守护)。
"""

import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.message.model import Message, MessageRole
from agentplatform.core.message.service import message_text

# 粗估 token:中文约 1.6 字/token、英文约 4 字符/token,取保守混合系数
_CHARS_PER_TOKEN = 2.5


def estimate_tokens(history: list[dict]) -> int:
    return int(sum(len(m.get("content", "")) for m in history) / _CHARS_PER_TOKEN)


async def _llm_summarize(client, prompt: str) -> str:
    """一次非交互式摘要调用:聚合 stream 事件文本。"""
    parts: list[str] = []
    async for e in client.stream(
        [{"role": "user", "content": prompt}],
    ):
        if e.type == "delta" and e.text:
            parts.append(e.text)
        elif e.type == "error":
            raise RuntimeError(f"摘要调用失败: {getattr(e, 'error', '')}")
    return "".join(parts).strip()


_SUMMARY_PROMPT = """请把以下对话历史压缩为一份简洁的滚动摘要,供 AI 助手后续对话时作为背景上下文。

要求:
1. **逐条保留用户声明的约束、偏好、目标与重要事实**(时间/数量/命名实体不得丢失);
2. 保留尚未完成的任务与待办;
3. 忽略寒暄与重复;
4. 用中文分条输出,不超过 300 字。

{existing}对话历史:
{history}
"""


async def maybe_compact_history(
    session: AsyncSession,
    session_id: uuid.UUID,
    history: list[dict],
    client,
) -> list[dict]:
    """阈值触发则压缩;返回注入摘要后的历史(未触发原样返回)。

    history 为 build_history 产物 [{role, content}];压缩后结构为
    [summary(以 user 角色注入,标注为上下文摘要)] + 最近 keep_recent 条。
    """
    max_tokens = getattr(settings, "context_compact_max_tokens", 24000)
    keep_recent = getattr(settings, "context_compact_keep_recent", 12)
    cooldown_s = 600  # 频率闸:10 分钟

    if estimate_tokens(history) <= max_tokens or len(history) <= keep_recent:
        return history

    # 频率闸:最近一次摘要 10 分钟内不重复压缩
    last = await session.scalar(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == MessageRole.summary,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    now = datetime.now(UTC)
    if last is not None and last.created_at and (now - last.created_at).total_seconds() < cooldown_s:
        return history

    evicted, kept = history[:-keep_recent], history[-keep_recent:]
    # 剔除 build_history 注入的旧摘要副本(以 summary 行为准,避免重复计入)
    evicted = [m for m in evicted if not m.get('content', '').startswith('(系统注入')]
    existing = ""
    if last is not None:
        existing = f"已有旧摘要(请合并保留其信息):\n{message_text(last)}\n\n"

    evicted_text = "\n".join(f"[{m['role']}] {m['content'][:800]}" for m in evicted)
    summary_text = await _llm_summarize(
        client, _SUMMARY_PROMPT.format(existing=existing, history=evicted_text)
    )
    if not summary_text:
        return history  # 摘要失败不阻塞对话

    # 滚动:同会话一条摘要行,原地更新
    if last is not None:
        last.blocks = [{"type": "markdown", "data": {"text": summary_text}}]
        last.created_at = now
    else:
        session.add(
            Message(
                session_id=session_id,
                role=MessageRole.summary,
                blocks=[{"type": "markdown", "data": {"text": summary_text}}],
            )
        )
    await session.flush()

    import logging as _log

    _log.getLogger(__name__).info(
        "上下文压缩: session=%s 淘汰 %d 条,估算 %d→%d tokens",
        session_id,
        len(evicted),
        estimate_tokens(history),
        estimate_tokens(kept) + int(len(summary_text) / _CHARS_PER_TOKEN),
    )
    return (
        [
            {
                "role": "user",
                "content": f"(系统注入:此前对话的上下文摘要,作为背景知识)\n{summary_text}",
            }
        ]
        + kept
    )
