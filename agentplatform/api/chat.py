"""对话 API(设计 005 §4)。

POST /chat/sessions/{sid}/messages 返回 SSE 流:delta / tool_call / done / error
(block_meta 等富交互事件在 M7 引入)。流结束后落库 assistant 最终消息。
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
    update_session,
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


async def _validate_mounted_kbs(
    session: AsyncSession, kb_ids: list[uuid.UUID], user: User
) -> list[uuid.UUID]:
    """挂载校验:库须存在且当前用户可读(设计 008 §4.2;授权在写入侧把关)。"""
    from agentplatform.core.kb import service as kb_service

    for kid in kb_ids:
        kb = await kb_service.get_kb(session, kid)
        if kb is None or not await kb_service.can_read(session, kb, str(user.id)):
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": "挂载的知识库不存在或不可读"},
            )
    return kb_ids


async def _with_default_shared_kb(
    session: AsyncSession, kb_ids: list[uuid.UUID], user: User
) -> list[uuid.UUID]:
    """新建会话默认挂载跨项目共享库(008 §11.3;slug 见 settings.kb_shared_workspace_slug,置空禁用)。"""
    from sqlalchemy import select as _select

    from agentplatform.config import settings
    from agentplatform.core.kb import service as kb_service
    from agentplatform.core.kb.model import KnowledgeBase

    slug = settings.kb_shared_workspace_slug
    if not slug:
        return kb_ids
    shared = await session.scalar(_select(KnowledgeBase).where(KnowledgeBase.slug == slug))
    if shared is None or not await kb_service.can_read(session, shared, str(user.id)):
        return kb_ids
    return kb_ids + [shared.id] if shared.id not in kb_ids else kb_ids


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_chat_session(
    payload: CreateSession,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> SessionOut:
    """创建会话(关联插件助手);response_model 负责序列化。"""
    mounted = await _validate_mounted_kbs(session, payload.mounted_kb_ids, user)
    mounted = await _with_default_shared_kb(session, mounted, user)
    row = await create_session(
        session, plugin_id=payload.plugin_id, user_id=str(user.id), mounted_kb_ids=mounted
    )
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
    """重命名会话标题 / 更新挂载知识库(M12)。"""
    await _ensure_session_owned(session, sid, user.id)
    mounted = (
        await _validate_mounted_kbs(session, payload.mounted_kb_ids, user)
        if payload.mounted_kb_ids is not None
        else None
    )
    row = await update_session(session, sid, title=payload.title, mounted_kb_ids=mounted)
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
    # 流前校验:会话不存在/无权访问必须以 HTTP 状态码快速失败,
    # 而非进入 SSE 后只在流内发 error 事件(设计 005 §错误契约)。
    await _ensure_session_owned(session, sid, user.id)
    # 多模态校验(设计 012):data:image 前缀 + 单张 5MB(与知识库单文档上限一致)
    import binascii

    for doc in payload.docs:
        if not doc.startswith("/api/files/raw"):
            raise HTTPException(
                status_code=422,
                detail={"code": "validation_error", "message": "docs 仅支持服务端文档 URL"},
            )
    for img in payload.images:
        if img.startswith("/api/files/raw"):  # 对象存储化后的服务端 URL
            continue
        if not img.startswith("data:image/"):
            raise HTTPException(
                status_code=422,
                detail={"code": "validation_error", "message": "仅支持图片(data:image/* 或服务端图片 URL)"},
            )
        try:
            size = len(binascii.a2b_base64(img.split(",", 1)[1]))
        except (binascii.Error, IndexError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail={"code": "validation_error", "message": "图片编码无效"}
            ) from exc
        if size > 5 * 1024 * 1024:
            raise HTTPException(
                status_code=422,
                detail={"code": "validation_error", "message": "单张图片不能超过 5MB"},
            )

    async def event_stream():
        text_parts: list[str] = []
        blocks: list[dict] = []

        try:
            usage_total: int | None = None
            async for ev in agent_stream_for_session(session, sid, payload.content, images=payload.images, docs=payload.docs):
                if ev.type == "reasoning" and ev.text:
                    yield sse("reasoning", {"text": ev.text})
                elif ev.type == "delta" and ev.text:
                    text_parts.append(ev.text)
                    yield sse("delta", {"block_index": 0, "text": ev.text})
                elif ev.type == "block_meta" and ev.block:
                    blocks.append(ev.block)
                    yield sse("block_meta", ev.block)
                elif ev.type == "await_external" and ev.block:
                    blocks.append(ev.block)
                    yield sse("await_external", ev.block)
                elif ev.type == "done" and ev.usage:
                    usage_total = ev.usage.get("total_tokens")
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
            usage_tokens = (usage_total or None)
            msg = await save_assistant_message(
                session, sid, final_blocks if final_blocks else final_text, tokens=usage_tokens
            )
            await session.commit()
            # 打磨:会话标题自动生成(独立会话/短任务,失败静默)
            import asyncio as _asyncio

            from agentplatform.core.message.service import generate_session_title

            _asyncio.get_running_loop().create_task(_generate_title_logged(sid, payload.content))
            yield sse(
                "done",
                {"message_id": str(msg.id), "tokens": usage_tokens},
            )

        except asyncio.CancelledError:
            # 打磨②:用户"停止生成"——已产出的部分文本落库(刷新不丢),再向上传播取消
            try:
                partial = "".join(text_parts)
                if partial.strip():
                    final_blocks: list[dict] = [{"type": "markdown", "data": {"text": partial}}]
                    final_blocks.extend(blocks)
                    await save_assistant_message(session, sid, final_blocks)
                    await session.commit()
            except Exception:  # noqa: BLE001
                await session.rollback()
            raise

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



@router.post("/sessions/{sid}/regenerate")
async def regenerate_last(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """重新生成最后一条助手回复(打磨②):撤回最后 assistant 消息,按最后 user 消息重跑。"""
    await _ensure_session_owned(session, sid, user.id)

    async def event_stream():
        text_parts: list[str] = []
        blocks: list[dict] = []
        try:
            from agentplatform.core.message.service import MessageRole

            msgs = await list_messages(session, sid)
            last_user = next((m for m in reversed(msgs) if m.role == MessageRole.user), None)
            last_asst = next((m for m in reversed(msgs) if m.role == MessageRole.assistant), None)
            if last_user is None:
                yield sse("error", {"code": "chat_error", "message": "没有可重新生成的用户消息"})
                return
            if last_asst is not None and msgs.index(last_asst) > msgs.index(last_user):
                await session.delete(last_asst)  # 撤回最后助手回复
                await session.flush()

            # 取最后 user 消息的文本与图片(blocks 内 image url)
            content = ""
            images: list[str] = []
            for b in last_user.blocks or []:
                if b.get("type") == "markdown":
                    content = (b.get("data") or {}).get("text", "")
                elif b.get("type") == "image":
                    images.append((b.get("data") or {}).get("url", ""))

            usage_total: int | None = None
            async for ev in agent_stream_for_session(
                session, sid, content, images=images or None, save_input=False
            ):
                if ev.type == "reasoning" and ev.text:
                    yield sse("reasoning", {"text": ev.text})
                elif ev.type == "delta" and ev.text:
                    text_parts.append(ev.text)
                    yield sse("delta", {"block_index": 0, "text": ev.text})
                elif ev.type == "block_meta" and ev.block:
                    blocks.append(ev.block)
                    yield sse("block_meta", ev.block)
                elif ev.type == "done" and ev.usage:
                    usage_total = ev.usage.get("total_tokens")
                elif ev.type == "tool_call" and ev.tool_trace is not None:
                    t = ev.tool_trace
                    yield sse(
                        "tool_call",
                        {"id": t.id, "name": t.name, "arguments": json.dumps(t.args, ensure_ascii=False), "result": t.result},
                    )
            final_text = "".join(text_parts)
            final_blocks: list[dict] = []
            if final_text.strip():
                final_blocks.append({"type": "markdown", "data": {"text": final_text}})
            final_blocks.extend(blocks)
            msg = await save_assistant_message(
                session, sid, final_blocks if final_blocks else final_text, tokens=usage_total
            )
            await session.commit()
            yield sse("done", {"message_id": str(msg.id), "tokens": usage_total})
        except ChatError as exc:
            await session.rollback()
            yield sse("error", {"code": "chat_error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            yield sse("error", {"code": "agent_error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{sid}/continue")
async def continue_after_interaction(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """交互回填(表单提交/确认等)后自动续跑:以最后一条 user 消息(交互回填文本,
    如【表单提交】/【交互确认】)作为当前轮触发 agent——不落新消息、不删历史,
    用户无需再手动输入"继续"。
    """
    await _ensure_session_owned(session, sid, user.id)

    async def event_stream():
        text_parts: list[str] = []
        blocks: list[dict] = []
        try:
            from agentplatform.core.message.service import MessageRole

            msgs = await list_messages(session, sid)
            last_user = next((m for m in reversed(msgs) if m.role == MessageRole.user), None)
            if last_user is None:
                yield sse("error", {"code": "chat_error", "message": "没有可续跑的交互回填消息"})
                return
            content = ""
            for b in last_user.blocks or []:
                if b.get("type") == "markdown":
                    content = (b.get("data") or {}).get("text", "")

            usage_total: int | None = None
            async for ev in agent_stream_for_session(session, sid, content, save_input=False):
                if ev.type == "reasoning" and ev.text:
                    yield sse("reasoning", {"text": ev.text})
                elif ev.type == "delta" and ev.text:
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
                elif ev.type == "done" and ev.usage:
                    usage_total = ev.usage.get("total_tokens")

            final_text = "".join(text_parts)
            final_blocks: list[dict] = []
            if final_text.strip():
                final_blocks.append({"type": "markdown", "data": {"text": final_text}})
            final_blocks.extend(blocks)
            msg = await save_assistant_message(
                session, sid, final_blocks if final_blocks else final_text, tokens=usage_total
            )
            await session.commit()
            yield sse("done", {"message_id": str(msg.id), "tokens": usage_total})
        except asyncio.CancelledError:
            try:
                partial = "".join(text_parts)
                if partial.strip():
                    await save_assistant_message(session, sid, [{"type": "markdown", "data": {"text": partial}}])
                    await session.commit()
            except Exception:  # noqa: BLE001
                await session.rollback()
            raise
        except ChatError as exc:
            await session.rollback()
            yield sse("error", {"code": "chat_error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            yield sse("error", {"code": "agent_error", "message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _generate_title_logged(sid: uuid.UUID, first_message: str) -> None:
    """后台生成会话标题;失败仅记日志(独立 Session)。"""
    import logging

    from agentplatform.core.db.engine import SessionLocal
    from agentplatform.core.message.service import generate_session_title

    try:
        async with SessionLocal() as db:
            title = await generate_session_title(db, sid, first_message)
            if title:
                logging.getLogger(__name__).info("会话标题已生成: %s -> %s", sid, title)
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception("会话标题生成失败 sid=%s", sid)


# ---------------------------------------------------------------- 会话分享(产品成熟度③)


class ShareOut(BaseModel):
    share_token: str
    share_url: str
    expires_at: str


@router.post("/sessions/{sid}/share", response_model=ShareOut)
async def create_share(
    sid: uuid.UUID,
    payload: dict | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> ShareOut:
    """创建只读分享链接(默认 7 天有效;再调一次重置 token)。"""
    await _ensure_session_owned(session, sid, user.id)
    import secrets
    from datetime import UTC, datetime, timedelta

    row = await get_session(session, sid)
    assert row is not None
    days = int((payload or {}).get("days") or 7)
    row.share_token = secrets.token_urlsafe(16)
    row.share_expires_at = datetime.now(UTC) + timedelta(days=days)
    await session.commit()
    return ShareOut(
        share_token=row.share_token,
        share_url=f"/share/{row.share_token}",
        expires_at=row.share_expires_at.isoformat(),
    )


@router.delete("/sessions/{sid}/share", status_code=204)
async def revoke_share(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
):
    """撤销分享链接。"""
    await _ensure_session_owned(session, sid, user.id)
    row = await get_session(session, sid)
    assert row is not None
    row.share_token = None
    row.share_expires_at = None
    await session.commit()


@router.get("/shared/{share_token}")
async def view_shared(
    share_token: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """公开只读视图(无需登录):会话标题 + 消息(不含用户身份字段)。"""
    from datetime import UTC, datetime

    from sqlalchemy import select as _select

    row = await session.scalar(_select(Session).where(Session.share_token == share_token))
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "分享不存在或已撤销"})
    if row.share_expires_at and row.share_expires_at < datetime.now(UTC):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "分享已过期"})
    msgs = []
    for m in await list_messages(session, row.id):
        txt = message_text(m)
        if m.role.value == "assistant" and not txt.strip():
            continue
        msgs.append({"role": m.role.value, "text": txt, "blocks": m.blocks or []})
    return {
        "title": row.title or "未命名会话",
        "created_at": row.created_at.isoformat(),
        "messages": msgs,
    }
