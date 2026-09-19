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
    docs: list[str] | None = None,
) -> Message:
    """用户消息落库;images(data:image dataURL)与 docs(服务端文档 URL)。"""
    blocks: list[dict] = []
    if content:
        blocks.append({"type": "markdown", "data": {"text": content}})
    for url in images or []:
        blocks.append({"type": "image", "data": {"url": url}})
    for url in docs or []:
        name = url.rsplit("/", 1)[-1].split("?")[0] or "document"
        blocks.append({"type": "file", "data": {"name": name, "url": url, "mime": "application/octet-stream"}})
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
    # 打磨:超长历史截断(最近 30 条),最早位置注入省略说明——避免 token 爆炸;
    # 完整的摘要压缩(早期轮次 LLM 摘要)留后续按需启用
    if len(history) > 30:
        omitted = len(history) - 30
        history = history[-30:]
        first = history[0]
        history[0] = {
            "role": first["role"],
            "content": f"(更早的 {omitted} 条对话已省略)\n{first['content']}",
        }
    return history


async def generate_session_title(
    session: AsyncSession, session_id: uuid.UUID, first_user_message: str
) -> str | None:
    """为会话生成短标题(打磨:告别"未命名会话")。

    用一次轻量 LLM 调用;失败静默(标题保持 null,不阻塞对话)。
    返回生成后的标题。
    """
    brief = first_user_message.strip().replace("\n", " ")[:200]
    if not brief:
        return None
    try:
        from agentplatform.core.chat.service import make_llm_client
        from agentplatform.core.session.service import get_session

        sess = await get_session(session, session_id)
        if sess is None or (sess.title and not sess.title.startswith("未命名")):
            return sess.title if sess else None  # 已有标题不覆盖
        client = await make_llm_client(session, None)
        parts: list[str] = []
        from agentplatform.core.agent.loop import _stream

        async for ev in _stream(
            client,
            [
                {
                    "role": "user",
                    "content": (
                        f"为下面的用户请求生成一个不超过 12 个字的中文会话标题,"
                        f"直接输出标题本身,不要引号和解释:\n\n{brief}"
                    ),
                }
            ],
            None,
        ):
            if ev.type == "delta" and ev.text:
                parts.append(ev.text)
        title = "".join(parts).strip().strip('"“”').replace("\n", " ")[:24]
        if title:
            sess.title = title
            await session.commit()
            return title
        return None
    except Exception:  # noqa: BLE001  标题失败不影响对话
        await session.rollback()
        return None
