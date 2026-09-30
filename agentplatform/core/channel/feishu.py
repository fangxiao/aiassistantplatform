"""飞书通道网关(M22,需求 012 / 设计 017)。

WebSocket 长连接接收 im.message.receive_v1(无需公网回调),文本消息桥接到
平台 chat 管线(与 Web 端同源,复用 agent_stream_for_session,含 P1 检查点),
回复以文本消息发回。未配置凭证时不启动(lifespan 判断)。

并发模型:lark ws 回调运行在 SDK 自己的线程,经 call_soon_threadsafe 投递到
asyncio 队列;worker 逐条消费,同一 chat_id 串行(需求 012 A4)——用
per-chat asyncio.Lock 保证,不同会话可并行。
"""

import asyncio
import json
import logging
import secrets
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings

logger = logging.getLogger(__name__)

FEISHU_SERVICE_EMAIL = "feishu-channel@agentplatform.local"
_INFLIGHT: dict[str, asyncio.Lock] = {}
_worker: asyncio.Task | None = None
_queue: asyncio.Queue | None = None
_ws_thread: object | None = None


async def _service_user_id(session: AsyncSession) -> str:
    """通道共享服务账号(get-or-create,role=user;需求 012 §5:独立账号 P2+)。"""
    from agentplatform.core.auth.model import UserRole
    from agentplatform.core.auth.service import create_user, get_user_by_email

    u = await get_user_by_email(session, FEISHU_SERVICE_EMAIL)
    if u is not None:
        return str(u.id)
    # 随机密码:通道账号不走密码登录,仅作会话归属
    u = await create_user(
        session,
        FEISHU_SERVICE_EMAIL,
        secrets.token_urlsafe(24),
        role=UserRole.user,
    )
    await session.commit()
    return str(u.id)


async def _bound_session_id(session: AsyncSession, chat_id: str) -> uuid.UUID | None:
    from agentplatform.core.channel.model import ChannelSession

    row = await session.scalar(
        select(ChannelSession).where(
            ChannelSession.channel == "feishu", ChannelSession.chat_id == chat_id
        )
    )
    return row.session_id if row is not None else None


async def _reset_binding(session: AsyncSession, chat_id: str) -> None:
    from agentplatform.core.channel.model import ChannelSession

    await session.execute(
        delete(ChannelSession).where(
            ChannelSession.channel == "feishu", ChannelSession.chat_id == chat_id
        )
    )
    await session.commit()


async def _ensure_session_id(session: AsyncSession, chat_id: str) -> uuid.UUID:
    """get-or-create:绑定存在即复用;否则以默认助手新建并落绑定。"""
    from agentplatform.core.channel.model import ChannelSession
    from agentplatform.core.plugin.model import Plugin
    from agentplatform.core.session.service import create_session

    sid = await _bound_session_id(session, chat_id)
    if sid is not None:
        return sid
    plugin_id: uuid.UUID | None = None
    if settings.feishu_default_plugin:
        plugin = await session.scalar(
            select(Plugin).where(Plugin.name == settings.feishu_default_plugin)
        )
        if plugin is not None:
            plugin_id = plugin.id
        else:
            logger.warning(
                "feishu_default_plugin=%s 不存在,回落默认助手",
                settings.feishu_default_plugin,
            )
    user_id = await _service_user_id(session)
    sess = await create_session(session, plugin_id=plugin_id, title="飞书会话", user_id=user_id)
    session.add(ChannelSession(channel="feishu", chat_id=chat_id, session_id=sess.id))
    await session.commit()
    return sess.id


def _extract_text(msg) -> str | None:
    """从事件消息体提取文本;仅处理文本类型,其余类型提示暂不支持。"""
    m = msg.event.message
    if getattr(m, "message_type", "") != "text":
        return None
    try:
        # SDK 模型字段为 content(payload 同名);首版误写 message_content,
        # AttributeError 被吞导致所有文本都落"暂只支持文本消息"(20260930)
        return json.loads(m.content).get("text", "")
    except (ValueError, AttributeError, TypeError):
        return None


def _reply_text(final_text: str, n_blocks: int) -> str:
    text = final_text.strip() or "（助手未返回文本内容）"
    if n_blocks:
        text += f"\n\n（本次回复含 {n_blocks} 个富交互组件,请在 Web 工作台查看与操作）"
    # 飞书单条文本上限 150KB,防御性截断
    return text[:60000]


async def _process(message_id: str, chat_id: str, text: str, reply_fn) -> None:
    """单条消息处理:命令分发 → 会话映射 → agent 运行 → 回复。"""
    from agentplatform.core.chat.service import agent_stream_for_session
    from agentplatform.core.db.session import SessionLocal

    cmd = text.strip()
    if cmd in ("/重置", "/reset"):
        async with SessionLocal() as s:
            await _reset_binding(s, chat_id)
        await reply_fn(message_id, "已开启新会话,上下文已清空。")
        return
    if cmd in ("/帮助", "/help", "帮助"):
        await reply_fn(
            message_id,
            "直接发消息即可与平台助手对话(上下文连续)。\n/重置 - 开启新会话\n/帮助 - 显示本帮助",
        )
        return

    lock = _INFLIGHT.setdefault(chat_id, asyncio.Lock())
    async with lock:  # A4:同一飞书会话串行处理
        try:
            async with SessionLocal() as s:
                sid = await _ensure_session_id(s, chat_id)
            parts: list[str] = []
            n_blocks = 0
            # 复用 Web 端的检查点 SSE 管道:助手消息随草稿检查点落库(需求 A5,
            # Web 端可见),断线路径行为一致;从 SSE 帧中提取增量文本
            from agentplatform.api.chat import _checkpointed_agent_sse

            async with SessionLocal() as s:
                agen = agent_stream_for_session(s, sid, text)
                async for frame in _checkpointed_agent_sse(s, sid, agen):
                    if frame.startswith("event: delta"):
                        payload = frame.split("data: ", 1)[1].strip()
                        parts.append(json.loads(payload).get("text", ""))
                    elif frame.startswith(("event: block_meta", "event: await_external")):
                        n_blocks += 1
                    elif frame.startswith("event: error"):
                        payload = frame.split("data: ", 1)[1].strip()
                        parts.append(f"\n[生成中断:{json.loads(payload).get('message', '')}]")
            await reply_fn(message_id, _reply_text("".join(parts), n_blocks))
        except Exception as exc:  # noqa: BLE001 通道侧兜底,错误必须回给用户
            logger.exception("feishu 通道处理失败 chat=%s", chat_id)
            try:
                await reply_fn(message_id, f"[处理失败] {type(exc).__name__}: {exc}")
            except Exception:  # noqa: BLE001
                pass


def _build_reply_fn(client) -> object:
    """构造回复函数:reply API 封装为 async(sync SDK 调用丢线程池)。"""
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        ReplyMessageRequest,
        ReplyMessageRequestBody,
    )

    async def reply(message_id: str, text: str) -> None:
        def _do() -> None:
            req = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(json.dumps({"text": text}, ensure_ascii=False))
                    .msg_type("text")
                    .build()
                )
                .build()
            )
            resp = client.im.v1.message.reply(req)
            if not resp.success():
                logger.warning(
                    "feishu 回复失败 code=%s msg=%s",
                    resp.code,
                    resp.msg,
                )

        await asyncio.get_running_loop().run_in_executor(None, _do)

    return reply


def start() -> bool:
    """启动飞书网关:凭证齐全才连(返回是否启动)。lifespan 调用。"""
    global _worker, _queue, _ws_thread

    if not (settings.feishu_app_id and settings.feishu_app_secret):
        logger.info("飞书通道未配置凭证,跳过启动")
        return False

    import lark_oapi as lark

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    client = (
        lark.Client.builder()
        .app_id(settings.feishu_app_id)
        .app_secret(settings.feishu_app_secret)
        .build()
    )

    def _on_message(data) -> None:
        try:
            msg = data.event.message
            if msg.chat_type != "p2p":
                return  # P2:群聊 @机器人
            text = _extract_text(data)
            if text is None:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    (msg.message_id, msg.chat_id, "__UNSUPPORTED__"),
                )
                return
            # 文本中可能带 @机器人 前缀(单聊通常没有),去掉再投递
            loop.call_soon_threadsafe(queue.put_nowait, (msg.message_id, msg.chat_id, text))
        except Exception:  # noqa: BLE001 事件回调不允许抛
            logger.exception("feishu 事件解析失败")

    async def _handle_unsupported() -> None:
        while True:
            item = await queue.get()
            try:
                message_id, chat_id, text = item
                if text == "__UNSUPPORTED__":
                    await _build_reply_fn(client)(message_id, "暂只支持文本消息,文件/图片等请在 Web 工作台发送。")
                else:
                    await _process(message_id, chat_id, text, _build_reply_fn(client))
            finally:
                queue.task_done()

    dispatcher = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message)
        .build()
    )

    _worker = asyncio.create_task(_handle_unsupported())
    _queue = queue

    def _run_ws() -> None:
        # SDK 的 ws client 在构造时会抓当前事件循环——必须在子线程内
        # 先设独立循环再构造,否则拿到主线程 uvicorn 正在跑的 uvloop,
        # start() 的 run_until_complete 直接 RuntimeError(20260930 首连即断根因)
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            # SDK 在 import 时抓了模块级全局 loop(主线程 uvicorn 运行中的循环),
            # start() 的 run_until_complete 会撞"already running"——线程内重指
            import lark_oapi.ws.client as _ws_mod

            _ws_mod.loop = asyncio.get_event_loop()
            ws_client = lark.ws.Client(
                settings.feishu_app_id,
                settings.feishu_app_secret,
                event_handler=dispatcher,
                log_level=lark.LogLevel.DEBUG,
            )
            ws_client.start()  # 阻塞运行;容器重启即停(trial 无优雅退出需求)
        except Exception:  # noqa: BLE001
            logger.exception("feishu 长连接退出")

    import threading

    _ws_thread = threading.Thread(target=_run_ws, name="feishu-ws", daemon=True)
    _ws_thread.start()
    logger.info("飞书通道已启动(WebSocket 长连接)")
    return True


async def stop() -> None:
    """停止 worker(ws 线程为 daemon,随进程退出)。"""
    global _worker
    if _worker is not None:
        _worker.cancel()
        _worker = None
