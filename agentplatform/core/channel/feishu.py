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
# 卡片发送器(start() 注入;命令处理里经 globals() 取用,便于测试替换)
_CARD_SENDER = None


def _text_card(content_md: str) -> dict:
    """简单文本卡片(占位/更新两用;lark_md 渲染)。"""
    return {
        "config": {"wide_screen_mode": True},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": content_md}}
        ],
    }


async def _create_card_with(client, chat_id: str, card: dict) -> str | None:
    """创建卡片消息,返回 message_id(占位卡用;失败返回 None 走文本降级)。"""
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )

    def _do() -> str | None:
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = client.im.v1.message.create(req)
        if resp.success() and resp.data is not None:
            return resp.data.message_id
        logger.warning("feishu 占位卡片创建失败 code=%s msg=%s", resp.code, resp.msg)
        return None

    return await asyncio.get_running_loop().run_in_executor(None, _do)


async def _patch_card_with(client, message_id: str, card: dict) -> bool:
    """更新卡片内容(占位卡 → 最终回答);失败返回 False 走文本降级。"""
    from lark_oapi.api.im.v1 import (
        PatchMessageRequest,
        PatchMessageRequestBody,
    )

    def _do() -> bool:
        req = (
            PatchMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                PatchMessageRequestBody.builder()
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = client.im.v1.message.patch(req)
        if resp.success():
            return True
        logger.warning("feishu 卡片更新失败 code=%s msg=%s", resp.code, resp.msg)
        return False

    return await asyncio.get_running_loop().run_in_executor(None, _do)


_PLACEHOLDER_CARD_NOTE = "⏳ 正在思考…\n\n长回答可能需要 10–30 秒,完成后此处直接显示答案。"


async def _send_text_with(client, chat_id: str, text: str) -> None:
    """向会话主动发送文本消息(卡片确认等场景,无 reply 目标时用)。"""
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )

    def _do() -> None:
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = client.im.v1.message.create(req)
        if not resp.success():
            logger.warning("feishu 主动文本发送失败 code=%s msg=%s", resp.code, resp.msg)

    await asyncio.get_running_loop().run_in_executor(None, _do)


async def _send_card_with(client, chat_id: str, card: dict) -> None:
    """向会话发送交互卡片(msg_type=interactive)。"""
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
    )

    def _do() -> None:
        req = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps(card, ensure_ascii=False))
                .build()
            )
            .build()
        )
        resp = client.im.v1.message.create(req)
        if not resp.success():
            raise RuntimeError(f"卡片发送失败: {resp.code} {resp.msg}")

    await asyncio.get_running_loop().run_in_executor(None, _do)


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


def _plugin_intro(plugin) -> str:
    """助手介绍(lark_md 文本):简介 + 技能/工具清单,切换成功即推送。"""
    m = plugin.manifest or {}
    label = m.get("display_name") or plugin.name
    lines = [f"✅ 已切换到 **{label}**（{plugin.name} v{plugin.version}）", ""]
    if m.get("description"):
        lines += [m["description"], ""]
    skills = m.get("skills") or []
    tools = m.get("tools") or []
    if skills:
        lines.append("**技能**")
        for x in skills:
            if not isinstance(x, dict):
                continue
            name = str(x.get("id", "")).split(":", 1)[-1]
            desc = (x.get("description") or "").strip()
            lines.append(f"· {name}{' — ' + desc[:48] if desc else ''}")
        lines.append("")
    if tools:
        lines.append("**工具**")
        for x in tools:
            if not isinstance(x, dict):
                continue
            name = str(x.get("id", "")).split(":", 1)[-1]
            desc = (x.get("description") or "").strip()
            lines.append(f"· {name}{' — ' + desc[:48] if desc else ''}")
        lines.append("")
    if not skills and not tools:
        lines.append("（该助手未声明独立技能/工具，直接描述你的需求即可）")
    lines.append("_直接发消息开始对话，上下文已重新开始_")
    return "\n".join(lines)


async def _switch_plugin(session: AsyncSession, chat_id: str, plugin_name: str):
    """切换助手:清旧绑定,以指定插件新建会话并绑定。返回 Plugin 或 None(未找到)。"""
    from sqlalchemy import select as _select

    from agentplatform.core.channel.model import ChannelSession
    from agentplatform.core.plugin.model import Plugin, PluginReviewStatus, PluginStatus
    from agentplatform.core.session.service import create_session

    plugin = await session.scalar(
        _select(Plugin).where(
            Plugin.name == plugin_name,
            Plugin.status == PluginStatus.active,
            Plugin.review_status == PluginReviewStatus.approved,
        )
    )
    if plugin is None:
        return None
    await _reset_binding(session, chat_id)
    user_id = await _service_user_id(session)
    sess = await create_session(
        session, plugin_id=plugin.id, title=f"飞书·{plugin.name}", user_id=user_id
    )
    session.add(ChannelSession(channel="feishu", chat_id=chat_id, session_id=sess.id))
    await session.commit()
    return plugin


async def _available_plugins() -> list:
    from agentplatform.core.db.session import SessionLocal
    from agentplatform.core.plugin.model import Plugin, PluginReviewStatus, PluginStatus
    from sqlalchemy import select as _select

    async with SessionLocal() as s:
        rows = (
            await s.scalars(
                _select(Plugin).where(
                    Plugin.status == PluginStatus.active,
                    Plugin.review_status == PluginReviewStatus.approved,
                ).order_by(Plugin.name)
            )
        ).all()
    return list(rows)


async def _list_plugins() -> str:
    rows = await _available_plugins()
    if not rows:
        return "当前没有可用的助手。"
    lines = ["可用助手:"]
    for r in rows:
        m = r.manifest or {}
        label = m.get("display_name") or r.name
        extra = f" — {m.get('description', '')[:24]}" if m.get("description") else ""
        lines.append(f"· {r.name}({label}){extra}")
    lines.append("\n/切换 <名字> 使用该助手(如 /切换 sharestudy)")
    return "\n".join(lines)


def _assistant_card_json(rows: list) -> dict:
    """助手选择卡片(经典 v1 卡片):select_static 选择即触发切换回调。"""
    options = []
    for r in rows:
        m = r.manifest or {}
        # 下拉只显示中文名(20260930 用户偏好);value 仍用插件名精确切换
        label = m.get("display_name") or r.name
        options.append(
            {
                "text": {"tag": "plain_text", "content": str(label)},
                "value": r.name,
            }
        )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "选择平台助手"},
            "template": "indigo",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "下拉选择即切换，对话上下文重新开始。",
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "select_static",
                        "name": "plugin",
                        "placeholder": {"tag": "plain_text", "content": "点击选择助手"},
                        "options": options,
                    }
                ],
            },
        ],
    }


async def _process(message_id: str, chat_id: str, text: str, reply_fn, client=None) -> None:
    """单条消息处理:命令分发 → 会话映射 → agent 运行 → 回复。"""
    from agentplatform.core.chat.service import agent_stream_for_session
    from agentplatform.core.db.session import SessionLocal

    cmd = text.strip()
    if not cmd:
        # 空文本(空消息/@残留等)不触发生成——曾引发 300s 空转超时(20260930)
        await reply_fn(message_id, "请输入内容后再发送。")
        return
    if cmd in ("/重置", "/reset"):
        async with SessionLocal() as s:
            await _reset_binding(s, chat_id)
        await reply_fn(message_id, "已开启新会话,上下文已清空。")
        return
    if cmd in ("/助手列表", "/助手", "/plugins"):
        # 优先发交互卡片(下拉选择即切换);失败回落文本列表
        card_sender = globals().get("_CARD_SENDER")
        rows = await _available_plugins()
        if card_sender is not None and rows:
            try:
                await card_sender(chat_id, _assistant_card_json(rows))
                return
            except Exception:  # noqa: BLE001  卡片失败回落文本
                logger.exception("飞书卡片发送失败,回落文本列表")
        await reply_fn(message_id, await _list_plugins())
        return
    if cmd.startswith("/切换"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await reply_fn(message_id, "用法:/切换 <助手名>(发送 /助手列表 查看)")
            return
        async with SessionLocal() as s:
            plugin = await _switch_plugin(s, chat_id, parts[1].strip())
        if plugin is None:
            await reply_fn(message_id, f"未找到可用助手:{parts[1].strip()}(发送 /助手列表 查看)")
            return
        intro = _plugin_intro(plugin)
        if client is not None:
            try:
                await _send_card_with(client, chat_id, _text_card(intro))
                return
            except Exception:  # noqa: BLE001  卡片失败回落文本
                logger.warning("feishu 介绍卡片发送失败,回落文本")
        await reply_fn(message_id, intro)
        return
    if cmd in ("/帮助", "/help", "帮助"):
        await reply_fn(
            message_id,
            "直接发消息即可与当前助手对话(上下文连续)。\n"
            "/助手列表 - 弹出助手选择卡片,下拉即切换\n"
            "/切换 <名字> - 切换助手(如 /切换 sharestudy)\n"
            "/重置 - 当前助手开新会话\n"
            "/帮助 - 显示本帮助",
        )
        return

    lock = _INFLIGHT.setdefault(chat_id, asyncio.Lock())
    async with lock:  # A4:同一飞书会话串行处理
        # 等待反馈(20260930 用户反馈"没有等待提示像没 work"):先发占位卡,
        # 生成完成后原地更新为答案;卡片不可用时静默降级为完成时一次性回复
        placeholder_mid: str | None = None
        if client is not None:
            try:
                placeholder_mid = await _create_card_with(
                    client, chat_id, _text_card(_PLACEHOLDER_CARD_NOTE)
                )
            except Exception:  # noqa: BLE001  占位失败不影响主流程
                logger.warning("feishu 占位卡片异常,降级为完成时回复")

        async def _deliver(final_text: str) -> None:
            if placeholder_mid is not None:
                try:
                    if await _patch_card_with(client, placeholder_mid, _text_card(final_text)):
                        return
                except Exception:  # noqa: BLE001  更新失败回落新消息
                    logger.warning("feishu 答案卡片更新异常,回落新消息")
            await reply_fn(message_id, final_text)

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
            await _deliver(_reply_text("".join(parts), n_blocks))
        except Exception as exc:  # noqa: BLE001 通道侧兜底,错误必须回给用户
            logger.exception("feishu 通道处理失败 chat=%s", chat_id)
            try:
                await _deliver(f"[处理失败] {type(exc).__name__}: {exc}")
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

    def _on_card_action(data):
        """卡片动作回调(长连接):下拉选择助手 → 投递 __CARD__ 项处理。"""
        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTriggerResponse,
            )

            ev = data.event
            a = ev.action
            option = None
            if a.form_value and a.form_value.get("plugin"):
                option = a.form_value["plugin"]
            elif a.option:
                option = a.option
            elif a.value and a.value.get("plugin"):
                option = a.value["plugin"]
            chat_id = ev.context.open_chat_id if ev.context else None
            open_message_id = (ev.context.open_message_id or "") if ev.context else ""
            if option and chat_id:
                # 队列项结构 (message_id, chat_id, text):切换标记必须放 text 槽位
                # ——曾误放 message_id 槽,worker 判 text 前缀永不命中,
                # 还把标记当 message_id 回复报 400(20260930 选助手无反应根因)
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    (open_message_id, chat_id, f"__CARD__:{option}"),
                )
            try:
                return P2CardActionTriggerResponse.build(
                    {"toast": {"type": "success", "content": "正在切换助手…"}}
                )
            except Exception:  # noqa: BLE001
                return None
        except Exception:  # noqa: BLE001 事件回调不允许抛
            logger.exception("feishu 卡片回调解析失败")
            return None

    async def _handle_unsupported() -> None:
        from agentplatform.core.db.session import SessionLocal as _SL

        while True:
            item = await queue.get()
            try:
                message_id, chat_id, text = item
                if text == "__UNSUPPORTED__":
                    await _build_reply_fn(client)(message_id, "暂只支持文本消息,文件/图片等请在 Web 工作台发送。")
                elif isinstance(text, str) and text.startswith("__CARD__:"):
                    plugin_name = text.split(":", 1)[1]
                    async with _SL() as s:
                        plugin = await _switch_plugin(s, chat_id, plugin_name)
                    if plugin is None:
                        await _send_text_with(
                            client, chat_id, f"未找到可用助手:{plugin_name}"
                        )
                    else:
                        # 切换成功即推助手介绍卡(20260930 用户建议:能做什么一目了然)
                        try:
                            await _send_card_with(
                                client, chat_id, _text_card(_plugin_intro(plugin))
                            )
                        except Exception:  # noqa: BLE001
                            await _send_text_with(client, chat_id, _plugin_intro(plugin))
                else:
                    await _process(message_id, chat_id, text, _build_reply_fn(client), client)
            except Exception:  # noqa: BLE001  单条消息失败绝不杀死 worker 循环
                # 20260930 事故:worker 无兜底,一轮异常即整通道静默(后续消息全部排队无响应)
                logger.exception("feishu worker 处理异常(已跳过该条)")
            finally:
                queue.task_done()

    dispatcher = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message)
        .register_p2_card_action_trigger(_on_card_action)
        .build()
    )
    global _CARD_SENDER
    _CARD_SENDER = lambda chat_id, card: _send_card_with(client, chat_id, card)  # noqa: E731

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
