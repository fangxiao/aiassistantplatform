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


async def _service_user_id(session: AsyncSession, open_id: str | None = None) -> str:
    """通道账号(P2-5):按飞书 open_id 自动开通独立平台账号(role=user,
    随机密码不可登录,仅作会话/资源归属);open_id 缺省回落共享服务账号。"""
    from agentplatform.core.auth.model import UserRole
    from agentplatform.core.auth.service import create_user, get_user_by_email

    email = (
        f"feishu-{open_id}@channel.agentplatform.local"
        if open_id
        else FEISHU_SERVICE_EMAIL
    )
    u = await get_user_by_email(session, email)
    if u is not None:
        return str(u.id)
    u = await create_user(session, email, secrets.token_urlsafe(24), role=UserRole.user)
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


async def _ensure_session_id(
    session: AsyncSession, chat_id: str, open_id: str | None = None, allowed: list | None = None
) -> uuid.UUID:
    """get-or-create:绑定存在即复用;否则以默认助手新建并落绑定(记录 open_id)。"""
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
    # allowlist(P2-4):机器人限定的助手范围内取默认插件
    if allowed and settings.feishu_default_plugin not in allowed:
        plugin_id = None
    user_id = await _service_user_id(session, open_id)
    sess = await create_session(session, plugin_id=plugin_id, title="飞书会话", user_id=user_id)
    session.add(
        ChannelSession(
            channel="feishu", chat_id=chat_id, session_id=sess.id, feishu_open_id=open_id
        )
    )
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


def _reply_text(final_text: str, n_blocks: int, unmapped_blocks: int = 0) -> str:
    text = final_text.strip() or "（助手未返回文本内容）"
    if unmapped_blocks:
        text += f"\n\n（另有 {unmapped_blocks} 个组件暂不支持飞书渲染,可在 Web 工作台查看）"
    # 飞书单条文本上限 150KB,防御性截断
    return text[:60000]


def _block_cards(block: dict, base_url: str = "") -> list[dict]:
    """展示类 ContentBlock → 飞书卡片(M23 P2):confirm/table/image/code/file。

    返回 0..N 张卡片;无法映射返回空列表(由调用方计数降级)。
    """
    btype = block.get("type") or ""
    data = block.get("data") or {}

    def _md_card(title: str | None, md: str, template: str = "turquoise") -> dict:
        els: list[dict] = []
        card: dict = {"config": {"wide_screen_mode": True}}
        if title:
            card["header"] = {
                "title": {"tag": "plain_text", "content": str(title)},
                "template": template,
            }
        els.append({"tag": "div", "text": {"tag": "lark_md", "content": md}})
        card["elements"] = els
        return card

    if btype == "input.confirm":
        message = str(data.get("message") or data.get("text") or "请确认")
        return [
            {
                "config": {"wide_screen_mode": True},
                "header": {
                    "title": {"tag": "plain_text", "content": "需要你确认"},
                    "template": "orange",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": message}},
                    {
                        "tag": "action",
                        "actions": [
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": str(data.get("confirm_text") or "确认")},
                                "type": "primary",
                                "value": {"__confirm_submit": 1, "confirmed": 1},
                            },
                            {
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": str(data.get("cancel_text") or "取消")},
                                "type": "danger",
                                "value": {"__confirm_submit": 1, "confirmed": 0},
                            },
                        ],
                    },
                ],
            }
        ]

    if btype == "table":
        cols = [str(c) for c in (data.get("columns") or [])]
        rows = [
            ["" if c is None else str(c) for c in (r if isinstance(r, list) else [])]
            for r in (data.get("rows") or [])
            if isinstance(r, list)
        ]
        if not cols:
            return []
        header_md = "|" + "|".join(cols) + "|\n|" + "|".join(["---"] * len(cols)) + "|"
        body_md = "\n".join("|" + "|".join(r) + "|" for r in rows)
        return [_md_card(data.get("title"), (header_md + "\n" + body_md).strip())]

    if btype == "image":
        url = str(data.get("url") or "")
        if not url:
            return []
        return [
            {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "img", "img_key": "", "alt": {"tag": "plain_text", "content": "图片"}}],
                # lark_md 中可直接嵌图片链接,退而求其次以链接展示
                "header": None,
            }
            if False
            else _md_card(data.get("title") or "图片", f"[查看图片]({url})")
        ]

    if btype == "code":
        code = str(data.get("code") or data.get("text") or "")
        lang = str(data.get("language") or "")
        return [
            {
                "config": {"wide_screen_mode": True},
                "elements": [
                    {
                        "tag": "code_block",
                        "language": lang or "plain_text",
                        "content": code[:20000],
                    }
                ],
            }
        ]

    if btype == "file":
        name = str(data.get("name") or "文件")
        url = str(data.get("url") or "")
        if not url:
            return []
        link = f"[{name}]({url})" if url.startswith("http") else name
        return [_md_card(None, f"📎 {link}")]

    return []


def _form_card(block: dict, sid: str) -> dict | None:
    """input.form → 飞书卡片表单(M23 P1 映射):提交回调 → 平台 interact → 续跑。

    支持 input.text/textarea/number→输入框、select/radio→下拉、date→日期;
    其余类型转普通输入框。无法映射返回 None(降级提示)。
    """
    data = block.get("data") or {}
    fields = data.get("fields") or []
    if not fields:
        return None
    elements: list[dict] = []
    for f in fields:
        fd = f.get("data") or {}
        key = str(fd.get("id") or f.get("id") or "")
        label = str(fd.get("label") or key)
        if not key:
            continue
        ftype = f.get("type") or "input.text"
        placeholder = {"tag": "plain_text", "content": label}
        if ftype in ("input.select", "input.radio"):
            options = [
                {"text": {"tag": "plain_text", "content": str(o)}, "value": str(o)}
                for o in (fd.get("options") or [])
            ]
            if options:
                elements.append(
                    {"tag": "select_static", "name": key, "placeholder": placeholder, "options": options}
                )
            else:
                elements.append({"tag": "input", "name": key, "placeholder": placeholder})
        elif ftype == "input.date":
            elements.append({"tag": "date_picker", "name": key, "placeholder": placeholder})
        else:
            elements.append({"tag": "input", "name": key, "placeholder": placeholder})
    if not elements:
        return None
    elements.append(
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": str(data.get("submit_text") or data.get("submit_label") or "提交")},
            "type": "primary",
            "action_type": "form_submit",
            "name": "submit",
            "value": {"__form_submit": 1, "sid": sid, "action": str(data.get("action") or "input.form")},
        }
    )
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": str(data.get("title") or "请填写以下信息")},
            "template": "blue",
        },
        "elements": [{"tag": "form", "name": "form", "elements": elements}],
    }


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


async def _switch_plugin(session: AsyncSession, chat_id: str, plugin_name: str, allowed: list | None = None, open_id: str | None = None):
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
    if plugin is None or (allowed and plugin_name not in allowed):
        return None
    await _reset_binding(session, chat_id)
    user_id = await _service_user_id(session, open_id)
    sess = await create_session(
        session, plugin_id=plugin.id, title=f"飞书·{plugin.name}", user_id=user_id
    )
    session.add(ChannelSession(channel="feishu", chat_id=chat_id, session_id=sess.id))
    await session.commit()
    return plugin


async def _available_plugins(allowed: list | None = None) -> list:
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
    if allowed:
        rows = [r for r in rows if r.name in allowed]
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


async def _process(message_id: str, chat_id: str, text: str, reply_fn, client=None, open_id: str | None = None, allowed: list | None = None) -> None:
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
        rows = await _available_plugins(allowed)
        if client is not None and rows:
            try:
                await _send_card_with(client, chat_id, _assistant_card_json(rows))
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
    if cmd.startswith("/定时"):
        await _handle_schedule_cmd(message_id, chat_id, cmd, reply_fn, open_id)
        return
    if cmd in ("/定时列表",):
        await _handle_schedule_cmd(message_id, chat_id, "/定时列表", reply_fn, open_id)
        return
    if cmd.startswith("/取消定时"):
        await _handle_schedule_cmd(message_id, chat_id, cmd, reply_fn, open_id)
        return
    if cmd in ("/帮助", "/help", "帮助"):
        await reply_fn(
            message_id,
            "直接发消息即可与当前助手对话(上下文连续)。\n"
            "/助手列表 - 弹出助手选择卡片,下拉即切换\n"
            "/切换 <名字> - 切换助手(如 /切换 sharestudy)\n"
            "/重置 - 当前助手开新会话\n"
            "/定时 HH:MM <内容> - 每天定点生成并推送到本会话\n"
            "/定时列表 / 取消定时 <名称> - 管理定时任务\n"
            "/帮助 - 显示本帮助",
        )
        return

    lock = _INFLIGHT.setdefault(chat_id, asyncio.Lock())
    async with lock:  # A4:同一飞书会话串行处理
        from agentplatform.core.db.session import SessionLocal as _SL

        async with _SL() as s:
            sid = await _ensure_session_id(s, chat_id, open_id, allowed)
        await _run_agent_round(client, chat_id, sid, text, message_id, reply_fn)


async def _run_agent_round(
    client, chat_id: str, sid: uuid.UUID, user_text: str, message_id: str, reply_fn
) -> None:
    """一轮 agent 运行与交付:占位卡 → 检查点管道流式 → 答案原地更新;
    input.form 渲染为飞书表单卡(M23 P1),其余组件计数降级提示。
    消息处理与表单提交续跑共用此路径。"""
    from agentplatform.core.chat.service import agent_stream_for_session
    from agentplatform.core.db.session import SessionLocal

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

    parts: list[str] = []
    blocks: list[dict] = []
    last_refresh = asyncio.get_running_loop().time()
    last_len = 0
    try:
        from agentplatform.api.chat import _checkpointed_agent_sse

        async with SessionLocal() as s:
            agen = agent_stream_for_session(s, sid, user_text)
            async for frame in _checkpointed_agent_sse(s, sid, agen):
                if frame.startswith("event: delta"):
                    payload = frame.split("data: ", 1)[1].strip()
                    parts.append(json.loads(payload).get("text", ""))
                    # 流式刷新(P2-1):节流 5s 增量 patch 占位卡,长回答渐进可见
                    now = asyncio.get_running_loop().time()
                    cur_len = sum(map(len, parts))
                    if (
                        placeholder_mid is not None
                        and now - last_refresh >= 5.0
                        and cur_len - last_len >= 20
                    ):
                        last_refresh = now
                        last_len = cur_len
                        try:
                            await _patch_card_with(
                                client,
                                placeholder_mid,
                                _text_card("".join(parts) + "\n\n_…(生成中)_"),
                            )
                        except Exception:  # noqa: BLE001  刷新失败不影响主流程
                            pass
                elif frame.startswith(("event: block_meta", "event: await_external")):
                    payload = frame.split("data: ", 1)[1].strip()
                    blocks.append(json.loads(payload))
                elif frame.startswith("event: error"):
                    payload = frame.split("data: ", 1)[1].strip()
                    parts.append(f"\n[生成中断:{json.loads(payload).get('message', '')}]")
        mappable = ("input.form", "input.confirm", "table", "image", "code", "file")
        handled = [b for b in blocks if isinstance(b, dict) and b.get("type") in mappable]
        unmapped = len(blocks) - len(handled)
        await _deliver(_reply_text("".join(parts), len(blocks), unmapped))
        from agentplatform.config import settings as _st

        base = getattr(_st, "public_api_base", "") or ""
        for b in handled:
            cards: list[dict] = []
            if b.get("type") == "input.form":
                c = _form_card(b, str(sid))
                cards = [c] if c else []
            else:
                cards = _block_cards(b, base)
            for card in cards:
                try:
                    if client is not None:
                        await _send_card_with(client, chat_id, card)
                except Exception:  # noqa: BLE001
                    logger.warning("feishu 组件卡片发送失败 type=%s", b.get("type"))
    except Exception as exc:  # noqa: BLE001 通道侧兜底,错误必须回给用户
        logger.exception("feishu 通道处理失败 chat=%s", chat_id)
        try:
            await _deliver(f"[处理失败] {type(exc).__name__}: {exc}")
        except Exception:  # noqa: BLE001
            pass




async def _handle_schedule_cmd(
    message_id: str, chat_id: str, cmd: str, reply_fn, open_id: str | None
) -> None:
    """定时任务命令(P2-3):以当前助手+通道账号创建,产出推回本会话。"""
    from agentplatform.core.db.session import SessionLocal as _SL
    from agentplatform.core.scheduler import service as sched
    from agentplatform.core.scheduler.model import ScheduledTask
    from sqlalchemy import select as _sel

    async def _current_plugin_and_user(s):
        row = await _bound_session_id(s, chat_id)
        plugin_id = None
        if row is not None:
            from agentplatform.core.session.service import get_session as _gs

            cs = await _gs(s, row)
            plugin_id = cs.plugin_id if cs else None
        user_id = await _service_user_id(s, open_id)
        return plugin_id, user_id

    if cmd == "/定时列表":
        async with _SL() as s:
            _, user_id = await _current_plugin_and_user(s)
            rows = (await s.scalars(_sel(ScheduledTask).where(ScheduledTask.user_id == user_id))).all()
        if not rows:
            await reply_fn(message_id, "暂无定时任务。/定时 HH:MM <内容> 创建")
            return
        lines = ["定时任务:"]
        for r in rows:
            when = r.daily_at or (f"每 {r.interval_minutes} 分钟" if r.interval_minutes else "?")
            lines.append(f"· {r.name}({when}) 下次 {r.next_run_at}")
        await reply_fn(message_id, "\n".join(lines)[:4000])
        return

    if cmd.startswith("/取消定时"):
        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            await reply_fn(message_id, "用法:/取消定时 <名称>")
            return
        async with _SL() as s:
            _, user_id = await _current_plugin_and_user(s)
            row = await s.scalar(
                _sel(ScheduledTask).where(
                    ScheduledTask.user_id == user_id, ScheduledTask.name == parts[1].strip()
                )
            )
            if row is None:
                await reply_fn(message_id, f"未找到定时任务:{parts[1].strip()}")
                return
            await sched.delete_task(s, user_id, row.id)
            await s.commit()
        await reply_fn(message_id, f"已取消定时任务:{parts[1].strip()}")
        return

    # /定时 HH:MM <内容>
    parts = cmd.split(maxsplit=2)
    if len(parts) < 3 or ":" not in parts[1]:
        await reply_fn(message_id, "用法:/定时 HH:MM <内容>(如 /定时 08:30 每日英语学习简报)")
        return
    hh_mm = parts[1].strip()
    content = parts[2].strip()
    try:
        hh, mm = (int(x) for x in hh_mm.split(":", 1))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except (ValueError, AssertionError):
        await reply_fn(message_id, "时间格式应为 HH:MM(如 08:30)")
        return
    async with _SL() as s:
        plugin_id, user_id = await _current_plugin_and_user(s)
        name = f"飞书定时-{hh_mm}"
        row = await sched.create_task(
            s,
            user_id=user_id,
            name=name,
            kind="custom",
            prompt=content,
            schedule_type="daily",
            daily_at=hh_mm,
            plugin_id=plugin_id,
        )
        row.feishu_chat_id = chat_id
        await s.commit()
    await reply_fn(
        message_id,
        f"已创建定时任务「{name}」:每天 {hh_mm} 以当前助手生成并推送到本会话。/定时列表 查看",
    )

async def push_to_chat(chat_id: str, title: str, text: str) -> bool:
    """向飞书会话推送卡片(定时任务产出等)。遍历已启动机器人,命中即返回。"""
    card = _text_card(f"**{title}**\n\n{text[:20000]}")
    for g in list(_GATEWAYS.values()):
        client = g.get("client")
        if client is None:
            continue
        try:
            await _send_card_with(client, chat_id, card)
            return True
        except Exception:  # noqa: BLE001  发错机器人(chat 不存在)静默跳过
            continue
    return False


async def _handle_confirm_submit(client, chat_id: str, payload: dict) -> None:
    """input.confirm 飞书按钮回执:确认/取消经 handle_interaction 落库后自动续跑。"""
    from agentplatform.core.db.session import SessionLocal
    from agentplatform.core.interact.service import handle_interaction

    async with SessionLocal() as s:
        sid = await _bound_session_id(s, chat_id)
    if sid is None:
        await _send_text_with(client, chat_id, "[确认异常] 当前会话无绑定")
        return
    confirmed = bool(payload.get("confirmed"))
    async with SessionLocal() as s:
        await handle_interaction(
            s,
            session_id=sid,
            block_id="feishu_confirm",
            action="input.confirm",
            value={"confirmed": confirmed},
        )
        await s.commit()
    note = "已确认,继续处理。" if confirmed else "已取消。"
    await _send_text_with(client, chat_id, note)


async def _handle_form_submit(client, chat_id: str, payload: dict) -> None:
    """飞书表单提交回执:fields 经 handle_interaction 落库(表格回执+【表单提交】
    用户消息),随后按 continue 语义自动续跑并交付答案。"""
    from agentplatform.core.db.session import SessionLocal
    from agentplatform.core.interact.service import handle_interaction
    from agentplatform.core.message.model import MessageRole
    from agentplatform.core.message.service import list_messages

    sid_str = str(payload.get("sid") or "")
    action = str(payload.get("action") or "input.form")
    form_value = payload.get("form_value") or {}
    if not sid_str:
        await _send_text_with(client, chat_id, "[表单提交异常] 缺少会话信息")
        return
    sid = uuid.UUID(sid_str)
    fields = [
        {"id": k, "label": k, "value": v} for k, v in form_value.items() if k != "submit"
    ]
    async with SessionLocal() as s:
        await handle_interaction(
            s, session_id=sid, block_id="feishu_form", action=action, value={"fields": fields}
        )
        await s.commit()
    content = ""
    async with SessionLocal() as s:
        msgs = await list_messages(s, sid)
        last_user = next((m for m in reversed(msgs) if m.role == MessageRole.user), None)
        if last_user is not None:
            for b in last_user.blocks or []:
                if isinstance(b, dict) and b.get("type") == "markdown":
                    content = (b.get("data") or {}).get("text", "")

    async def _fallback_reply(message_id: str, text: str) -> None:
        await _send_text_with(client, chat_id, text)

    lock = _INFLIGHT.setdefault(chat_id, asyncio.Lock())
    async with lock:
        await _run_agent_round(client, chat_id, sid, content, "", _fallback_reply)


def _start_bot(app_id: str, app_secret: str, allowed: list | None, name: str = "") -> dict:
    """启动单个飞书机器人网关(WS 线程 + 队列 + worker)。返回句柄。

    P2-4:多机器人并存;allowed 为该机器人可用的助手插件名列表(None=不限)。
    队列项 (message_id, chat_id, text, open_id):open_id 用于按飞书用户
    自动开通通道账号(P2-5)。
    """
    import threading

    import lark_oapi as lark

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    client = (
        lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
    )

    def _put(item: tuple) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, item)

    def _on_message(data) -> None:
        try:
            msg = data.event.message
            sender = getattr(getattr(data.event, "sender", None), "sender_id", None)
            open_id = getattr(sender, "open_id", "") or ""
            text = _extract_text(data)
            if msg.chat_type != "p2p":
                # 群聊(P2-6):仅 @机器人 的文本触发
                if text is None:
                    return
                import re as _re

                stripped = _re.sub(r"<at[^>]*>\s*</at>", "", text).strip()
                mentions = getattr(msg, "mentions", None)
                at_bot = bool(mentions) or "@_user" in text or stripped != text
                if not at_bot or not stripped:
                    return
                _put((msg.message_id, msg.chat_id, stripped, open_id))
                return
            if text is None:
                _put((msg.message_id, msg.chat_id, "__UNSUPPORTED__", open_id))
                return
            _put((msg.message_id, msg.chat_id, text, open_id))
        except Exception:  # noqa: BLE001  事件回调不允许抛
            logger.exception("feishu 事件解析失败")

    def _toast(text: str):
        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTriggerResponse,
            )

            return P2CardActionTriggerResponse.build(
                {"toast": {"type": "success", "content": text}}
            )
        except Exception:  # noqa: BLE001
            return None

    def _on_card_action(data):
        """卡片动作回调:确认按钮 / 表单提交 / 助手下拉,统一投递队列。"""
        try:
            ev = data.event
            a = ev.action
            chat_id0 = ev.context.open_chat_id if ev.context else None
            open_mid = (ev.context.open_message_id or "") if ev.context else ""
            if not a.form_value and isinstance(a.value, dict) and a.value.get("__confirm_submit"):
                if chat_id0:
                    _put(
                        (
                            open_mid,
                            chat_id0,
                            "__CONFIRM__:"
                            + json.dumps({"confirmed": bool(a.value.get("confirmed"))}, ensure_ascii=False),
                            "",
                        )
                    )
                return _toast("已记录,继续处理…")
            if a.form_value and isinstance(a.value, dict) and a.value.get("__form_submit"):
                if chat_id0:
                    _put(
                        (
                            open_mid,
                            chat_id0,
                            "__FORM__:"
                            + json.dumps(
                                {"sid": a.value.get("sid"), "action": a.value.get("action"), "form_value": a.form_value},
                                ensure_ascii=False,
                            ),
                            "",
                        )
                    )
                return _toast("已提交,正在生成…")
            option = None
            if a.form_value and a.form_value.get("plugin"):
                option = a.form_value["plugin"]
            elif a.option:
                option = a.option
            elif a.value and a.value.get("plugin"):
                option = a.value["plugin"]
            if option and chat_id0:
                _put((open_mid, chat_id0, f"__CARD__:{option}", ""))
            return _toast("正在切换助手…")
        except Exception:  # noqa: BLE001  事件回调不允许抛
            logger.exception("feishu 卡片回调解析失败")
            return None

    async def _worker_loop() -> None:
        from agentplatform.core.db.session import SessionLocal as _SL

        while True:
            item = await queue.get()
            try:
                message_id, chat_id, text, open_id = item
                if text == "__UNSUPPORTED__":
                    await _build_reply_fn(client)(message_id, _unsupported_reply())
                elif isinstance(text, str) and text.startswith("__CONFIRM__:"):
                    try:
                        payload = json.loads(text.split(":", 1)[1])
                    except ValueError:
                        payload = {"confirmed": False}
                    await _handle_confirm_submit(client, chat_id, payload)
                elif isinstance(text, str) and text.startswith("__FORM__:"):
                    try:
                        payload = json.loads(text.split(":", 1)[1])
                    except ValueError:
                        payload = {}
                    await _handle_form_submit(client, chat_id, payload)
                elif isinstance(text, str) and text.startswith("__CARD__:"):
                    plugin_name = text.split(":", 1)[1]
                    async with _SL() as s:
                        plugin = await _switch_plugin(s, chat_id, plugin_name, allowed, open_id)
                    if plugin is None:
                        await _send_text_with(client, chat_id, f"未找到可用助手:{plugin_name}")
                    else:
                        try:
                            await _send_card_with(client, chat_id, _text_card(_plugin_intro(plugin)))
                        except Exception:  # noqa: BLE001
                            await _send_text_with(client, chat_id, _plugin_intro(plugin))
                else:
                    await _process(
                        message_id, chat_id, text, _build_reply_fn(client), client, open_id, allowed
                    )
            except Exception:  # noqa: BLE001  单条消息失败绝不杀死 worker 循环
                logger.exception("feishu worker 处理异常(已跳过该条)")
            finally:
                queue.task_done()

    dispatcher = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(_on_message)
        .register_p2_card_action_trigger(_on_card_action)
        .build()
    )

    worker = asyncio.create_task(_worker_loop())

    def _run_ws() -> None:
        # SDK ws client 抓循环问题:子线程独立循环 + 重指模块级全局(20260930)
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
            import lark_oapi.ws.client as _ws_mod

            _ws_mod.loop = asyncio.get_event_loop()
            ws_client = lark.ws.Client(
                app_id,
                app_secret,
                event_handler=dispatcher,
                log_level=lark.LogLevel.INFO,
            )
            ws_client.start()
        except Exception:  # noqa: BLE001
            logger.exception("feishu 长连接退出 bot=%s", name or app_id)

    thread = threading.Thread(target=_run_ws, name=f"feishu-ws-{name or app_id}", daemon=True)
    thread.start()
    logger.info("飞书机器人已启动:%s(%s)", name or app_id, app_id)
    handle = {"app_id": app_id, "queue": queue, "worker": worker, "thread": thread, "client": client}
    return handle


def _unsupported_reply() -> str:
    return "该消息类型暂不支持,请发送文本(文件/语音支持建设中)。"


_GATEWAYS: dict[str, dict] = {}


async def _load_bots() -> list[dict]:
    """启用的机器人列表:DB 配置优先;无 DB 配置时回落 settings 全局凭证。"""
    try:
        from agentplatform.core.channel.model import FeishuBot
        from agentplatform.core.db.session import SessionLocal as _SL
        from agentplatform.core.llm.crypto import decrypt
        from sqlalchemy import select as _select

        async with _SL() as s:
            rows = (
                await s.scalars(_select(FeishuBot).where(FeishuBot.enabled.is_(True)))
            ).all()
        out = []
        for r in rows:
            try:
                secret = decrypt(r.app_secret_enc)
            except Exception:  # noqa: BLE001  解密失败跳过该机器人
                logger.warning("feishu bot %s secret 解密失败,跳过", r.name)
                continue
            out.append(
                {"app_id": r.app_id, "app_secret": secret, "allowed": r.allowed_plugins, "name": r.name}
            )
        return out
    except Exception:  # noqa: BLE001  DB 未就绪不阻塞启动
        logger.warning("feishu bots 加载失败(表未迁移?)")
        return []


def start() -> bool:
    """启动飞书网关(lifespan):DB 机器人 + settings 全局凭证(回退兼容)。"""
    async def _boot() -> list[str]:
        bots = []
        if settings.feishu_app_id and settings.feishu_app_secret:
            bots.append(
                {
                    "app_id": settings.feishu_app_id,
                    "app_secret": settings.feishu_app_secret,
                    "allowed": None,
                    "name": "default(settings)",
                }
            )
        bots.extend(await _load_bots())
        ids = []
        for b in bots:
            if b["app_id"] in _GATEWAYS:
                continue
            try:
                _GATEWAYS[b["app_id"]] = _start_bot(
                    b["app_id"], b["app_secret"], b["allowed"], b.get("name", "")
                )
                ids.append(b["app_id"])
            except Exception:  # noqa: BLE001  单机器人失败不影响其他
                logger.exception("feishu 机器人启动失败 %s", b.get("name"))
        return ids

    # start() 在 lifespan(异步上下文)中调用:同步派发启动任务
    asyncio.get_running_loop().create_task(_boot())
    if not (settings.feishu_app_id or settings.feishu_app_secret):
        logger.info("飞书通道未配置凭证;等待 DB 机器人配置或跳过")
    return True


def start_bot_now(bot: dict) -> None:
    """管理接口:立即启动/重启一个机器人(增改后调用)。"""
    gid = bot["app_id"]
    old = _GATEWAYS.pop(gid, None)
    if old is not None:
        old["worker"].cancel()
    _GATEWAYS[gid] = _start_bot(gid, bot["app_secret"], bot.get("allowed"), bot.get("name", ""))


def stop_bot_now(app_id: str) -> None:
    """管理接口:停用一个机器人(删除/禁用后调用;WS 线程 daemon 随进程退出)。"""
    old = _GATEWAYS.pop(app_id, None)
    if old is not None:
        old["worker"].cancel()


async def stop() -> None:
    """停止全部 worker(ws 线程为 daemon,随进程退出)。"""
    for g in list(_GATEWAYS.values()):
        g["worker"].cancel()
    _GATEWAYS.clear()
