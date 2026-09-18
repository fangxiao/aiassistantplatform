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


async def save_user_message(
    session: AsyncSession,
    session_id: uuid.UUID,
    content: str,
    images: list[str] | None = None,
) -> Message:
    """用户消息落库;images(设计 012)为 data:image/* dataURL,渲染走 ImageRenderer。"""
    blocks: list[dict] = []
    if content:
        blocks.append({"type": "markdown", "data": {"text": content}})
    for url in images or []:
        blocks.append({"type": "image", "data": {"url": url}})
    if not blocks:
        blocks = [{"type": "markdown", "data": {"text": ""}}]
    msg = Message(
        session_id=session_id,
        role=MessageRole.user,
        blocks=blocks,
    )
    session.add(msg)
    await session.flush()
    return msg


async def save_assistant_message(
    session: AsyncSession,
    session_id: uuid.UUID,
    content: str | list[dict],
    tokens: int | None = None,
) -> Message:
    if isinstance(content, list):
        blocks = content
    else:
        blocks = [{"type": "markdown", "data": {"text": content}}]
    msg = Message(
        session_id=session_id,
        role=MessageRole.assistant,
        blocks=blocks,
        tokens=tokens,
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
    """组装 agent 输入历史 [{role, content}],仅 user/assistant 且非空且无思考标签消息。"""
    import re

    history: list[dict] = []
    for m in await list_messages(session, session_id):
        if m.role not in (MessageRole.user, MessageRole.assistant):
            continue
        txt = message_text(m)
        if not txt or not txt.strip():
            continue
        # 剔除思考过程与松散标签
        clean_txt = re.sub(r"<think>[\s\S]*?</think>", "", txt)
        clean_txt = re.sub(r"</?think>", "", clean_txt).strip()
        if not clean_txt:
            continue
        history.append({"role": m.role.value, "content": clean_txt})
    return history
