"""通知出口(产品成熟度④):邮件(SMTP)与 webhook。

定时任务(ScheduledTask.notify)产出后推送;失败仅记日志不影响任务本身。
"""

import logging

import httpx

from agentplatform.config import settings

logger = logging.getLogger(__name__)


async def send_webhook(url: str, payload: dict) -> bool:
    """POST JSON 到任意 webhook(飞书自定义机器人/企微/Slack 兼容格式由调用方构造)。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        logger.warning("notify: webhook 失败 %s: %s", url, exc)
        return False


def send_email(to: str, subject: str, body: str) -> bool:
    """SMTP 纯文本邮件(同步 smtplib;量小无碍)。未配置 SMTP 返回 False。"""
    if not settings.notify_smtp_host:
        return False
    import smtplib
    from email.header import Header
    from email.mime.text import MIMEText

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = settings.notify_from or settings.notify_smtp_user
        msg["To"] = to
        with smtplib.SMTP_SSL(settings.notify_smtp_host, settings.notify_smtp_port) as srv:
            srv.login(settings.notify_smtp_user, settings.notify_smtp_pass)
            srv.sendmail(msg["From"], [to], msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("notify: 邮件失败 to=%s: %s", to, exc)
        return False


def feishu_bot_payload(text: str) -> dict:
    """构造飞书自定义机器人消息体(msg_type=text)。"""
    return {"msg_type": "text", "content": {"text": text}}
