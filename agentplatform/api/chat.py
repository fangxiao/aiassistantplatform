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
from agentplatform.core.agent.errors import classify_exception
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
from agentplatform.core.message.model import Message, MessageRole
from agentplatform.core.message.service import (
    build_history,
    finalize_draft_message,
    latest_draft_message,
    list_messages,
    message_text,
    save_assistant_message,
    update_draft_progress,
)
from agentplatform.core.plugin.loader import is_plugin_visible
from agentplatform.core.plugin.model import Plugin
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
    """校验会话存在且属于当前用户(admin 豁免——通道会话归服务账号,
    admin 需在 Web 端查看/打开,需求 012 A5);否则 404/403。"""
    row = await get_session(session, sid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"会话不存在: {sid}"},
        )
    if row.user_id and str(row.user_id) != str(user_id):
        # admin 豁免:通道会话归服务账号,admin 需在 Web 端查看/打开(需求 012 A5)
        from agentplatform.core.auth.dependencies import is_admin
        from agentplatform.core.auth.model import User as _User

        current = await session.get(_User, user_id)
        if current is None or not is_admin(current):
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
    """创建会话(关联插件助手);未过审助手仅 owner/admin 可开(015 §5)。"""
    if payload.plugin_id is not None:
        plugin = await session.get(Plugin, payload.plugin_id)
        if plugin is not None and not is_plugin_visible(plugin, user):
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": f"助手不存在或未启用: {payload.plugin_id}"},
            )
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
    scope: str = "mine",
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> list[SessionOut]:
    """我的会话列表;scope=channel(admin)返回飞书通道会话(需求 012 A5)。"""
    if scope == "channel":
        from agentplatform.core.auth.dependencies import is_admin

        if not is_admin(user):
            raise HTTPException(
                status_code=403,
                detail={"code": "forbidden", "message": "仅管理员可查看通道会话"},
            )
        from agentplatform.core.auth.service import get_user_by_email
        from agentplatform.core.channel.feishu import FEISHU_SERVICE_EMAIL

        svc = await get_user_by_email(session, FEISHU_SERVICE_EMAIL)
        if svc is None:
            return []
        rows = await list_sessions(session, user_id=str(svc.id))
        return [SessionOut.model_validate(r, from_attributes=True) for r in rows]
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
    row = await update_session(
        session, sid, title=payload.title, mounted_kb_ids=mounted,
        model_override=payload.model_override,
        model_override_clear=payload.model_override_clear,
    )
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
    """会话历史消息(summary 行不渲染为气泡,经 /summary 端点查看,ADR 0011)。"""
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
        if m.role != MessageRole.summary
    ]


@router.get("/sessions/{sid}/summary")
async def context_summary(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> dict:
    """上下文滚动摘要(可知情入口,需求 011 A3);无摘要返回空。"""
    await _ensure_session_owned(session, sid, user.id)
    from sqlalchemy import select as _sel

    row = await session.scalar(
        _sel(Message)
        .where(Message.session_id == sid, Message.role == MessageRole.summary)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return {"text": message_text(row) if row is not None else None}


_DRAFT_FLUSH_CHARS = 4000  # 检查点 flush 的正文增量阈值(工具边界为主,此为纯长文本兜底)


async def _persist_interrupted_tail(
    sid: uuid.UUID,
    draft_id: uuid.UUID | None,
    blocks: list[dict],
    is_final: bool,
) -> None:
    """断开路径的尾部落盘:必须用独立 DB 会话与独立任务。

    断开发生在 starlette/anyio 的取消作用域内——请求作用域的 session 上任何
    await(含 except 块里的 flush/commit)都会被立即再取消,原地落库必被静默
    回滚(20260929 P1 冒烟实测)。派生脱离该作用域的任务 + 全新会话才可靠。
    """
    from datetime import timedelta as _td

    from agentplatform.core.db.session import SessionLocal

    async with SessionLocal() as s:
        d = await s.get(Message, draft_id) if draft_id is not None else None
        if d is None:
            d = Message(
                session_id=sid,
                role=MessageRole.assistant,
                blocks=[{"type": "markdown", "data": {"text": ""}}],
                is_draft=True,
            )
            s.add(d)
            await s.flush()
            d.created_at = d.created_at + _td(microseconds=2000)
        d.blocks = blocks or [{"type": "markdown", "data": {"text": ""}}]
        if is_final:
            d.is_draft = False
        await s.commit()
        import logging as _log

        _log.getLogger(__name__).info(
            "断开尾部落盘完成: session=%s message=%s is_final=%s", sid, d.id, is_final
        )




async def _record_round_trace(
    session: AsyncSession,
    sid: uuid.UUID,
    message_id: uuid.UUID | None,
    tokens: int | None,
    error_kind,
    error_detail: str | None,
) -> None:
    """轮次轨迹落库(需求 011 H4):主会话可能已 rollback,用独立会话写。"""
    from agentplatform.core.agent.errors import ErrorKind
    from agentplatform.core.agent.trace_model import AgentRoundTrace
    from agentplatform.core.db.session import SessionLocal

    try:
        async with SessionLocal() as s2:
            s2.add(
                AgentRoundTrace(
                    session_id=sid,
                    message_id=message_id,
                    kind="chat",
                    tokens=tokens,
                    error_kind=error_kind.value if isinstance(error_kind, ErrorKind) else error_kind,
                    error_detail=error_detail,
                )
            )
            await s2.commit()
    except Exception:  # noqa: BLE001  trace 失败不影响主流程
        import logging as _log

        _log.getLogger(__name__).warning("agent_round_trace 写入失败 session=%s", sid)


async def _checkpointed_agent_sse(
    session: AsyncSession,
    sid: uuid.UUID,
    agent_events,
    *,
    draft: Message | None = None,
    is_resume: bool = False,
    title_source: str | None = None,
):
    """消费 agent 事件流转 SSE,附草稿检查点(设计 016 §2 / ADR 0009 / P1)。

    - 流开始若无草稿则创建(is_draft=True);
    - tool_call 边界与正文增量阈值处 flush 草稿——断线时已产出内容留存为检查点;
    - done:finalize 草稿转正式消息;
    - 用户取消(CancelledError):partial 转正式(与既有"停止生成"行为一致);
    - 其他异常:partial 留在草稿(is_draft 保持),error 事件带 resumable + message_id,
      取代旧"rollback 整轮丢弃"行为(20260929 断流事故的整轮消失即源于此)。
    """
    text_parts: list[str] = []
    blocks: list[dict] = []
    # resume 时保留草稿已有内容为前缀,续跑产物追加其后
    base_blocks: list[dict] = list(draft.blocks or []) if draft is not None else []
    usage_total: int | None = None
    flushed_len = 0
    draft_id: uuid.UUID | None = draft.id if draft is not None else None

    def _spawn_tail(is_final: bool) -> None:
        """把未 flush 的尾部派生独立任务落盘(见 _persist_interrupted_tail)。"""
        text = "".join(text_parts)
        if is_final:
            from agentplatform.core.agent.img_proxy import sanitize_model_images

            text = sanitize_model_images(text)
        composed = [*base_blocks]
        if text.strip():
            composed.append({"type": "markdown", "data": {"text": text}})
        composed.extend(blocks)
        if draft_id is None and not text.strip() and not blocks:
            return  # 无草稿且无内容,无需落盘
        asyncio.get_running_loop().create_task(
            _persist_interrupted_tail(sid, draft_id, composed, is_final)
        )

    def _composed(is_final: bool) -> list[dict]:
        final_text = "".join(text_parts)
        if is_final:
            from agentplatform.core.agent.img_proxy import sanitize_model_images

            final_text = sanitize_model_images(final_text)
        composed = [*base_blocks]
        if final_text.strip():
            composed.append({"type": "markdown", "data": {"text": final_text}})
        composed.extend(blocks)
        return composed

    async def _ensure_draft() -> None:
        """惰性建草稿:首个内容事件时才落库——agent_stream_for_session 是惰性
        生成器,用户消息在首次迭代时才保存;草稿必须晚于它创建,否则
        list_messages 按 created_at 排序会把 assistant 排到 user 之前。
        首 token 前断开本就无可检查点内容,惰性创建无损失。"""
        nonlocal draft, draft_id
        if draft is not None:
            return
        draft = await save_assistant_message(
            session, sid, [{"type": "markdown", "data": {"text": ""}}], is_draft=True
        )
        draft_id = draft.id
        # 与用户消息可能同微秒落库,后移 2ms 保证 user → assistant 严格顺序
        from datetime import timedelta as _td

        draft.created_at = draft.created_at + _td(microseconds=2000)
        await session.flush()
        await session.commit()

    async def _flush(is_final: bool = False) -> None:
        nonlocal draft
        if draft is None and not (text_parts or blocks):
            return  # 无内容不建空草稿(避免污染会话与 resume 定位)
        await _ensure_draft()
        if is_final:
            await finalize_draft_message(session, draft, _composed(True), tokens=usage_total)
        else:
            await update_draft_progress(session, draft, _composed(False))

    try:
        if draft is not None and is_resume:
            yield sse("resume_started", {"message_id": str(draft.id)})
        async for ev in agent_events:
            if ev.type == "reasoning" and ev.text:
                yield sse("reasoning", {"text": ev.text})
            elif ev.type == "delta" and ev.text:
                text_parts.append(ev.text)
                yield sse("delta", {"block_index": 0, "text": ev.text})
                if sum(map(len, text_parts)) - flushed_len >= _DRAFT_FLUSH_CHARS:
                    await _flush()
                    await session.commit()
                    flushed_len = sum(map(len, text_parts))
            elif ev.type == "block_meta" and ev.block:
                blocks.append(ev.block)
                yield sse("block_meta", ev.block)
            elif ev.type == "await_external" and ev.block:
                blocks.append(ev.block)
                yield sse("await_external", ev.block)
            elif ev.type == "tool_call" and ev.tool_trace is not None:
                t = ev.tool_trace
                # 先 flush 后 yield:客户端恰在此事件处断开时,检查点必须已落库
                await _flush()
                await session.commit()
                flushed_len = sum(map(len, text_parts))
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
                usage_total = ev.usage.get("total_tokens") or usage_total
        await _flush(is_final=True)
        await session.commit()
        await _record_round_trace(
            session, sid, draft.id if draft is not None else None, usage_total, None, None
        )
        if title_source is not None:
            import asyncio as _asyncio

            _asyncio.get_running_loop().create_task(
                _generate_title_logged(sid, title_source)
            )
        done_payload = {"message_id": str(draft.id), "tokens": usage_total}
        if is_resume:
            done_payload["resume_of"] = str(draft.id)
        yield sse("done", done_payload)

    except GeneratorExit:
        # 客户端断开:starlette 经 aclose 关闭流生成器,以 GeneratorExit 在
        # yield 点穿透。anyio 取消作用域内不可原地 await 落库(会被再取消),
        # 派生独立任务 + 独立会话落盘尾部;partial 转正式(与用户停止行为一致)
        _spawn_tail(is_final=True)
        raise

    except asyncio.CancelledError:
        # 任务取消:同上,派生独立任务落盘,partial 转正式
        _spawn_tail(is_final=True)
        raise

    except ChatError as exc:
        kind, _resumable = classify_exception(exc)
        try:
            await _flush()
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
        await _record_round_trace(
            session, sid, draft.id if draft is not None else None, usage_total, kind, str(exc)[:500]
        )
        yield sse(
            "error",
            {
                "code": "chat_error",
                "kind": kind.value,
                "message": str(exc),
                "resumable": draft is not None,
                "message_id": str(draft.id) if draft is not None else None,
            },
        )
    except Exception as exc:  # noqa: BLE001  SSE 内兜底,避免连接悬挂
        kind, _resumable = classify_exception(exc)
        try:
            await _flush()
            await session.commit()
        except Exception:  # noqa: BLE001
            await session.rollback()
        await _record_round_trace(
            session, sid, draft.id if draft is not None else None, usage_total, kind, str(exc)[:500]
        )
        yield sse(
            "error",
            {
                "code": "agent_error",
                "kind": kind.value,
                "message": str(exc),
                "resumable": draft is not None,
                "message_id": str(draft.id) if draft is not None else None,
            },
        )


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
        agent_events = agent_stream_for_session(
            session, sid, payload.content, images=payload.images, docs=payload.docs
        )
        async for chunk in _checkpointed_agent_sse(
            session, sid, agent_events, title_source=payload.content
        ):
            yield chunk

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
            # T18.15 图片溯源清洗:编造/失效的 <img> 确定性替换占位图(最终防线)
            from agentplatform.core.agent.img_proxy import sanitize_model_images

            final_text = sanitize_model_images(final_text)
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
        agent_events = agent_stream_for_session(session, sid, content, save_input=False)
        async for chunk in _checkpointed_agent_sse(session, sid, agent_events):
            yield chunk

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{sid}/resume")
async def resume_interrupted(
    sid: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """断点续跑(设计 016 §2 / ADR 0009 / P1):定位最后一条草稿消息,以
    「含草稿的完整历史 + 内部续跑指令」重启 agent,产物原地并入草稿 finalize。
    已完成轮次与工具调用随历史保留,不重跑、不重复计费。
    """
    await _ensure_session_owned(session, sid, user.id)

    draft = await latest_draft_message(session, sid)
    if draft is None:
        # 无草稿:中断发生在首个产出之前(用户消息已落库,LLM 未答)——
        # 回退为重跑最后一条用户消息,同样实现"无需手动重发"(A1 完整闭环)
        msgs = await list_messages(session, sid)
        last_user = next(
            (m for m in reversed(msgs) if m.role == MessageRole.user), None
        )
        if last_user is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "no_draft", "message": "没有可续跑的中断草稿"},
            )
        fallback_content = message_text(last_user)
        if not fallback_content.strip():
            raise HTTPException(
                status_code=404,
                detail={"code": "no_draft", "message": "没有可续跑的中断草稿"},
            )

        async def event_stream():
            history = await build_history(session, sid)
            agent_events = agent_stream_for_session(
                session,
                sid,
                fallback_content,
                save_input=False,
                prior_history=history[:-1] if history else [],
            )
            async for chunk in _checkpointed_agent_sse(session, sid, agent_events):
                yield chunk

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        # 历史含草稿内容(build_history 收 assistant 消息),模型从部分回答处继续
        history = await build_history(session, sid)
        directive = (
            "【系统】上一条回复因连接中断未完成。请从中断处继续完成回答,"
            "不要重复已输出的内容,保持风格与结构连贯。"
        )
        agent_events = agent_stream_for_session(
            session,
            sid,
            directive,
            save_input=False,
            prior_history=history,
        )
        async for chunk in _checkpointed_agent_sse(session, sid, agent_events, draft=draft, is_resume=True):
            yield chunk

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
