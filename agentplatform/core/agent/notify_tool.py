"""主动触达工具 tool:notify_user(20261015,方案 B)。

插件在对话或定时轮次中调用,把即时消息推送到当前用户已配置的通知通道
(飞书 webhook/webhook/email,见 core/notify)。与定时任务的首行 [ALERT]
文本约定互补:本工具可在轮次中途结构化告警,不必等整轮结束。

限流:每用户每小时最多 NOTIFY_HOURLY_LIMIT 次(进程内滑动窗口),防骚扰。
"""

import json
import time
from collections import defaultdict, deque

from sqlalchemy import or_, select

from agentplatform.core.notify.model import NotificationChannel

NOTIFY_TOOL_ID = "tool:notify_user"

NOTIFY_HOURLY_LIMIT = 10

RESOURCE: dict = {
    "id": NOTIFY_TOOL_ID,
    "kind": "tool",
    "name": "notify_user",
    "version": "1.0.0",
    "description": (
        "主动推送通知给当前用户(飞书/webhook/email,取其已配置的启用通道)。"
        "用于:限时情报提醒、长任务完成、异常告警等需要即时触达的场景。"
        "普通信息用 normal;需要用户立即处理的紧急事项用 alert(推送侧强提醒)。"
        "用户未配置任何通知通道时返回提示,引导其到工作台配置。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "通知标题(一句话)"},
                "message": {"type": "string", "description": "通知正文,简洁给出要点"},
                "level": {
                    "type": "string",
                    "enum": ["normal", "alert"],
                    "description": "normal=普通;alert=紧急(强提醒)",
                },
            },
            "required": ["title", "message"],
        },
        "returns": {"type": "string", "description": "推送结果 JSON:ok/sent/channels"},
    },
}

# 进程内滑动窗口限流:user_id -> deque[timestamp]
_send_times: dict[str, deque] = defaultdict(deque)


def _rate_limited(user_id: str) -> bool:
    now = time.time()
    window = _send_times[user_id]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= NOTIFY_HOURLY_LIMIT:
        return True
    window.append(now)
    return False


async def run(args: dict, user_id: str | None = None) -> str:
    """推送通知到用户启用的通知通道;返回 JSON 回填 agent loop。"""
    if not user_id:
        return json.dumps(
            {"ok": False, "error": "缺少执行者身份,无法确定通知目标"}, ensure_ascii=False
        )
    title = str(args.get("title") or "").strip()
    message = str(args.get("message") or "").strip()
    level = str(args.get("level") or "normal").strip().lower()
    if not title or not message:
        return json.dumps(
            {"ok": False, "error": "title 与 message 均不能为空"}, ensure_ascii=False
        )
    if level not in ("normal", "alert"):
        level = "normal"
    if _rate_limited(user_id):
        return json.dumps(
            {
                "ok": False,
                "error": f"已达每小时 {NOTIFY_HOURLY_LIMIT} 次推送上限,请稍后再试",
            },
            ensure_ascii=False,
        )

    from agentplatform.core.db.engine import SessionLocal
    from agentplatform.core.notify.service import deliver

    text = f"[ALERT] {title}\n{message}" if level == "alert" else f"{title}\n{message}"
    async with SessionLocal() as db:
        channels = (
            await db.scalars(
                select(NotificationChannel).where(
                    or_(
                        NotificationChannel.user_id == user_id,
                        NotificationChannel.user_id.is_(None),
                    ),
                    NotificationChannel.enabled.is_(True),
                )
            )
        ).all()

    if not channels:
        return json.dumps(
            {
                "ok": False,
                "error": "当前用户未配置任何通知通道;请引导用户到工作台「通知通道」添加(飞书机器人/webhook/email)",
            },
            ensure_ascii=False,
        )

    sent_names: list[str] = []
    for ch in channels:
        try:
            if await deliver(ch, text):
                sent_names.append(ch.name)
        except Exception:  # noqa: BLE001  单通道失败不阻断
            continue
    return json.dumps(
        {
            "ok": len(sent_names) > 0,
            "sent": len(sent_names),
            "total": len(channels),
            "channels": sent_names,
            "level": level,
        },
        ensure_ascii=False,
    )
