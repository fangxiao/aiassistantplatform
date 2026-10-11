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


async def send_form(url: str, data: dict) -> bool:
    """POST 表单编码(Server酱协议要求 x-www-form-urlencoded,JSON 不认)。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, data=data)
            return resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        logger.warning("notify: form webhook 失败 %s: %s", url, exc)
        return False


def send_email(to: str, subject: str, body: str, html: str | None = None) -> bool:
    """SMTP 邮件(同步 smtplib;量小无碍)。html 非空时发 multipart(按钮可点)。
    未配置 SMTP 返回 False。"""
    if not settings.notify_smtp_host:
        return False
    import smtplib
    from email.header import Header
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    try:
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
        else:
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


def _split_title(text: str, limit: int) -> tuple[str, str]:
    """首行作推送标题(微信卡片只露标题),余下全文进正文。"""
    lines = text.strip().splitlines()
    title = (lines[0].strip() if lines else "通知")[:limit]
    return title, text.strip()


def serverchan_payload(text: str) -> dict:
    """Server酱(form 字段,sc.ftqq.com 协议):title ≤32 字,desp 收 markdown 全文。"""
    title, desp = _split_title(text, 32)
    return {"title": title, "desp": desp}


def pushplus_payload(text: str, token: str) -> dict:
    """pushplus(JSON body):token 经 webhook URL query 传入(…/send?token=xxx)。"""
    title, content = _split_title(text, 100)
    return {"token": token, "title": title, "content": content, "template": "txt"}


async def send_task_webhook(url: str, payload_kind: str, text: str, task_name: str) -> bool:
    """任务产出 → 自定义 webhook,按消息格式分派(M34:新增微信推送 Server酱/pushplus)。

    学生场景里飞书/邮件到不了人,微信服务号是唯一日常入口;两类服务都走
    "粘贴个人推送地址"的低门槛接入,凭据由学生各自申请。
    """
    from urllib.parse import parse_qs, urlparse

    # 空 kind(存量任务无该字段)保持旧契约 raw,不默认 feishu
    kind = (payload_kind or "").lower()
    if kind == "serverchan":
        return await send_form(url, serverchan_payload(text))
    if kind == "pushplus":
        query = parse_qs(urlparse(url).query)
        token = (query.get("token") or [""])[0]
        if not token:
            logger.warning("notify: pushplus 地址缺少 token query 参数 %s", url)
            return False
        return await send_webhook(url, pushplus_payload(text, token))
    if kind == "feishu":
        return await send_webhook(url, feishu_bot_payload(text))
    return await send_webhook(url, {"task": task_name, "output": text[:4000]})


async def deliver(channel, text: str) -> bool:
    """按通道类型分派推送。channel 为 NotificationChannel(或 duck-typed dict)。"""
    ctype = getattr(channel, "type", None) or (channel.get("type") if isinstance(channel, dict) else "")
    cfg = getattr(channel, "config", None) or (channel.get("config") if isinstance(channel, dict) else {})
    url = str(cfg.get("url") or "")
    if ctype == "feishu_webhook" and url:
        return await send_webhook(url, feishu_bot_payload(text))
    if ctype == "webhook" and url:
        return await send_webhook(url, {"text": text})
    if ctype == "email" and cfg.get("email"):
        return send_email(str(cfg["email"]), "AgentPlatform 通知", text)
    logger.warning("notify: 未知或配置不全的通道类型 %r", ctype)
    return False
