"""对话 API(设计 005 §4)。

POST /chat/sessions/{sid}/messages 返回 SSE 流:delta / tool_call / done / error
(block_meta 等富交互事件在 M7 引入)。流结束后落库 assistant 最终消息。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.chat.schemas import (
    CreateSession,
    MessageOut,
    SendMessage,
    SessionOut,
    UpdateSession,
)
from agentplatform.core.chat.service import ChatError, agent_stream_for_session
from agentplatform.core.chat.sse import sse
from agentplatform.core.db.session import get_session as get_db_session
from agentplatform.core.interact.errors import InteractError
from agentplatform.core.interact.schemas import (
    EventRequest,
    EventResponse,
    InteractRequest,
    InteractResponse,
)
from agentplatform.core.interact.service import handle_interaction, record_event
from agentplatform.core.message.service import (
    list_messages,
    message_text,
    save_assistant_message,
)
from agentplatform.core.session.model import Session
from agentplatform.core.session.service import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session_title,
)

router = APIRouter(prefix="/chat", tags=["chat"])


async def _ensure_session_owned(
    session: AsyncSession, sid: uuid.UUID, user_id: uuid.UUID
) -> Session:
    """校验会话存在且属于当前用户;否则 404/403。"""
    row = await get_session(session, sid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"会话不存在: {sid}"},
        )
    if row.user_id and str(row.user_id) != str(user_id):
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "无权访问该会话"},
        )
    return row


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_chat_session(
    payload: CreateSession,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """创建会话(关联插件助手);response_model 负责序列化。"""
    row = await create_session(session, plugin_id=payload.plugin_id, user_id=str(user.id))
    out = SessionOut.model_validate(row, from_attributes=True)
    await session.commit()
    return out


@router.get("/sessions", response_model=list[SessionOut])
async def chat_sessions(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[SessionOut]:
    """我的会话列表。"""
    rows = await list_sessions(session, user_id=str(user.id))
    return [SessionOut.model_validate(r, from_attributes=True) for r in rows]


@router.delete("/sessions/{sid}")
async def remove_session(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除会话。"""
    await _ensure_session_owned(session, sid, user.id)
    await delete_session(session, sid)
    await session.commit()
    return {"ok": True}


@router.patch("/sessions/{sid}", response_model=SessionOut)
async def rename_session(
    sid: uuid.UUID,
    payload: UpdateSession,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """重命名会话标题。"""
    await _ensure_session_owned(session, sid, user.id)
    row = await update_session_title(session, sid, payload.title)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "会话不存在"})
    out = SessionOut.model_validate(row, from_attributes=True)
    await session.commit()
    return out



@router.get("/sessions/{sid}/messages", response_model=list[MessageOut])
async def history_messages(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    """会话历史消息。"""
    await _ensure_session_owned(session, sid, user.id)
    return [
        MessageOut(
            id=m.id,
            role=m.role.value,
            text=message_text(m),
            blocks=m.blocks,
            created_at=m.created_at,
        )
        for m in await list_messages(session, sid)
    ]


@router.post("/sessions/{sid}/messages")
async def send_message(
    sid: uuid.UUID,
    payload: SendMessage,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """发送消息,返回 SSE 流(响应消息生成)。"""
    await _ensure_session_owned(session, sid, user.id)

    async def event_stream():
        text_parts: list[str] = []
        blocks: list[dict] = []
        try:
            async for ev in agent_stream_for_session(session, sid, payload.content):
                if ev.type == "delta" and ev.text:
                    text_parts.append(ev.text)
                    yield sse("delta", {"block_index": 0, "text": ev.text})
                elif ev.type == "block_meta" and ev.block:
                    blocks.append(ev.block)
                    yield sse("block_meta", ev.block)
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
            final_text = "".join(text_parts)
            final_blocks: list[dict] = []
            if final_text.strip():
                final_blocks.append({"type": "markdown", "data": {"text": final_text}})
            final_blocks.extend(blocks)
            msg = await save_assistant_message(
                session, sid, final_blocks if final_blocks else final_text
            )
            await session.commit()
            yield sse("done", {"message_id": str(msg.id)})

        except ChatError as exc:
            await session.rollback()
            yield sse("error", {"code": "chat_error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001  SSE 内兜底,避免连接悬挂
            await session.rollback()
            yield sse("error", {"code": "agent_error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/sessions/{sid}/blocks/{bid}/interact", response_model=InteractResponse)
async def submit_block_interaction(
    sid: uuid.UUID,
    bid: str,
    payload: InteractRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> InteractResponse:
    """交互回传接口(设计 003 v2.0 §9.1)。用户在 ContentBlock 上操作后提交。"""
    await _ensure_session_owned(session, sid, user.id)
    try:
        blocks = await handle_interaction(
            session,
            session_id=sid,
            block_id=bid,
            action=payload.action,
            args=payload.args,
            value=payload.value,
        )
        return InteractResponse(blocks=blocks)
    except InteractError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.post("/sessions/{sid}/events", response_model=EventResponse)
async def submit_event(
    sid: uuid.UUID,
    payload: EventRequest,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> EventResponse:
    """轻反馈事件接口(如 thumbs 点赞/点踩)。"""
    await _ensure_session_owned(session, sid, user.id)
    await record_event(
        session,
        session_id=sid,
        kind_str=payload.kind,
        block_id=payload.target_block_id,
        value=payload.value,
    )
    return EventResponse(ok=True)

