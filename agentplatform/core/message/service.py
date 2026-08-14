"""消息服务(设计 004 §messages / 003 v2.0 §3 消息信封)。

保存/查询消息;从 blocks(ContentBlock 列表)提取文本供 agent 历史使用,
无 blocks 时回退历史 content(003 v2.0 §3.4 兼容)。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.message.model import Message, MessageRole


def blocks_to_text(blocks: list | None) -> str:
    """从 ContentBlock 列表提取 markdown 文本。"""
    if not blocks:
        return ""
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "markdown":
            text = (b.get("data") or {}).get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def message_text(m: Message) -> str:
    """消息文本:优先 blocks,回退历史 content。"""
    text = blocks_to_text(m.blocks)
    if text:
        return text
    if isinstance(m.content, dict):
        return str(m.content.get("text", ""))
    if isinstance(m.content, str):
        return m.content
    return ""


async def save_user_message(session: AsyncSession, session_id: uuid.UUID, content: str) -> Message:
    msg = Message(
        session_id=session_id,
        role=MessageRole.user,
        blocks=[{"type": "markdown", "data": {"text": content}}],
    )
    session.add(msg)
    await session.flush()
    return msg


async def save_assistant_message(session: AsyncSession, session_id: uuid.UUID, text: str) -> Message:
    msg = Message(
        session_id=session_id,
        role=MessageRole.assistant,
        blocks=[{"type": "markdown", "data": {"text": text}}],
    )
    session.add(msg)
    await session.flush()
    return msg


async def list_messages(
    session: AsyncSession, session_id: uuid.UUID
) -> list[Message]:
    rows = await session.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(rows)


async def build_history(
    session: AsyncSession, session_id: uuid.UUID
) -> list[dict]:
    """组装 agent 输入历史 [{role, content}],仅 user/assistant。"""
    history: list[dict] = []
    for m in await list_messages(session, session_id):
        if m.role not in (MessageRole.user, MessageRole.assistant):
            continue
        history.append({"role": m.role.value, "content": message_text(m)})
    return history
