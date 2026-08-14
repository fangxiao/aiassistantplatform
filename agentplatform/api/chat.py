"""对话 API(设计 005 §4)。

POST /chat/sessions/{sid}/messages 返回 SSE 流:delta / tool_call / done / error
(block_meta 等富交互事件在 M7 引入)。流结束后落库 assistant 最终消息。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.chat.schemas import (
    CreateSession,
    MessageOut,
    SendMessage,
    SessionOut,
)
from agentplatform.core.chat.service import ChatError, agent_stream_for_session
from agentplatform.core.chat.sse import sse
from agentplatform.core.db.session import get_session as get_db_session
from agentplatform.core.message.service import (
    list_messages,
    message_text,
    save_assistant_message,
)
from agentplatform.core.session.model import Session
from agentplatform.core.session.service import (
    create_session,
    get_session,
    list_sessions,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_chat_session(
    payload: CreateSession,
    session: AsyncSession = Depends(get_db_session),
) -> Session:
    """创建会话(关联插件助手);response_model 负责序列化。"""
    row = await create_session(session, plugin_id=payload.plugin_id)
    await session.commit()
    return row


@router.get("/sessions", response_model=list[SessionOut])
async def chat_sessions(
    session: AsyncSession = Depends(get_db_session),
) -> list[Session]:
    """我的会话列表。"""
    return await list_sessions(session)


@router.get("/sessions/{sid}/messages", response_model=list[MessageOut])
async def history_messages(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> list[MessageOut]:
    """会话历史消息。"""
    if await get_session(session, sid) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"会话不存在: {sid}"},
        )
    return [
        MessageOut(
            id=m.id, role=m.role.value, text=message_text(m), created_at=m.created_at
        )
        for m in await list_messages(session, sid)
    ]


@router.post("/sessions/{sid}/messages")
async def send_message(
    sid: uuid.UUID,
    payload: SendMessage,
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    """发送消息,返回 SSE 流(响应消息生成)。"""
    if await get_session(session, sid) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"会话不存在: {sid}"},
        )

    async def event_stream():
        text_parts: list[str] = []
        try:
            async for ev in agent_stream_for_session(session, sid, payload.content):
                if ev.type == "delta" and ev.text:
                    text_parts.append(ev.text)
                    yield sse("delta", {"block_index": 0, "text": ev.text})
                elif ev.type == "tool_call" and ev.tool_trace is not None:
                    t = ev.tool_trace
                    yield sse(
                        "tool_call",
                        {
                            "kind": t.id.split(":", 1)[0],
                            "name": t.id,
                            "args": t.args,
                            "result": t.result,
                        },
                    )
            msg = await save_assistant_message(session, sid, "".join(text_parts))
            await session.commit()
            yield sse("done", {"message_id": str(msg.id)})
        except ChatError as exc:
            await session.rollback()
            yield sse("error", {"code": "chat_error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001  SSE 内兜底,避免连接悬挂
            await session.rollback()
            yield sse("error", {"code": "agent_error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
