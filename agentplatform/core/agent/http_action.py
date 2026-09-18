"""tool:http_request —— 通用 HTTP 动作(M17,设计 014 §1)。

agent 的"手":调用外部 HTTP API(发消息/查数据)。安全链:
域名白名单(settings.action_http_allowlist,空=禁用)→ 协议白名单 →
SSRF DNS 级拦截(复用 connectors.web 判定)→ 执行(15s 超时/256KB 截断)。
拒绝均返回 JSON 给 LLM(可向用户解释),不抛异常。
"""

import json
from urllib.parse import urlparse

import httpx

from agentplatform.config import settings

HTTP_ACTION_TOOL_ID = "tool:http_request"

_MAX_RESPONSE_BYTES = 256 * 1024

# 写操作确认闸门(M17 P1):pending 一次性、进程内、TTL 10 分钟。
# 确认者是会话属主(interact 端点已校验会话所有权)——人工闸门不可被 LLM 绕过。
_PENDING: dict[str, dict] = {}
_PENDING_TTL_S = 600
_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

RESOURCE: dict = {
    "id": HTTP_ACTION_TOOL_ID,
    "kind": "tool",
    "name": "http_request",
    "version": "1.0.0",
    "description": (
        "调用外部 HTTP API 执行动作(发送消息/查询数据等)。"
        "仅允许管理员配置的白名单域名;调用前先确认 URL 在允许范围内。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                "url": {"type": "string", "description": "完整 URL(https://)"},
                "headers": {"type": "object", "description": "可选,请求头"},
                "body": {"type": "string", "description": "可选,请求体(JSON 字符串或文本)"},
            },
            "required": ["method", "url"],
        },
        "returns": {"type": "string", "description": "响应状态与内容(JSON,截断至 256KB)"},
    },
}


def _allowlisted(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False, f"仅允许 http/https 协议: {parsed.scheme or '(空)'}"
    allow = [h.lower().strip() for h in settings.action_http_allowlist if h.strip()]
    if not allow:
        return False, (
            "动作能力未启用:需管理员配置 ACTION_HTTP_ALLOWLIST 域名白名单"
            "(当前为空,所有请求被拒绝)"
        )
    if host not in allow:
        return False, f"域名 {host} 不在动作白名单内(允许: {', '.join(allow)})"
    return True, ""


async def run(args: dict) -> str:
    method = str(args.get("method") or "GET").upper()
    url = str(args.get("url") or "").strip()
    if not url:
        return json.dumps({"ok": False, "error": "url 不能为空"}, ensure_ascii=False)

    # 写操作确认闸门:写方法先挂起,等会话属主在确认框点击(loop 特判渲染 input.confirm)
    if method in _WRITE_METHODS and settings.action_require_confirm and not args.get("__skip_gate__"):
        import time
        import uuid as _uuid

        confirm_id = _uuid.uuid4().hex[:12]
        body_brief = (str(args.get("body") or "")[:120]) or "(无请求体)"
        digest = f"{method} {url}\n请求体: {body_brief}"
        _PENDING[confirm_id] = {
            "args": {**args, "method": method, "url": url},
            "digest": digest,
            "created_at": time.time(),
        }
        return json.dumps(
            {
                "pending": True,
                "confirm_id": confirm_id,
                "digest": digest,
                "message": (
                    "该请求为写操作,已挂起等待用户在确认框中确认;"
                    "请向用户说明将要执行的操作并等待其点击确认/取消,不要自行重复调用"
                ),
            },
            ensure_ascii=False,
        )

    ok, reason = _allowlisted(url)
    if not ok:
        return json.dumps({"ok": False, "error": reason}, ensure_ascii=False)

    # SSRF:DNS 解析后逐 IP 复查(与网页连接器同判定;含协议/host 校验)
    from agentplatform.core.kb.connectors.web import _assert_url_safe

    try:
        await _assert_url_safe(httpx.AsyncClient(), url)
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    except Exception:  # noqa: BLE001  DNS 失败等
        return json.dumps(
            {"ok": False, "error": f"目标主机不可解析: {urlparse(url).hostname}"}
        , ensure_ascii=False)

    headers = {str(k): str(v) for k, v in (args.get("headers") or {}).items()}
    body = args.get("body")
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            resp = await client.request(
                method, url, headers=headers,
                content=body if body is not None else None,
                json=None,
            )
        text = resp.text
        if len(text.encode()) > _MAX_RESPONSE_BYTES:
            text = text[:_MAX_RESPONSE_BYTES] + "...[截断]"
        return json.dumps(
            {"ok": resp.status_code < 400, "status": resp.status_code,
             "body": text, "note": "调用已执行;请勿重复执行同一写操作"},
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"ok": False, "error": f"请求失败: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )


async def confirm_and_run(confirm_id: str, approved: bool) -> str:
    """确认框回填入口(interact 分发):一次性取出 pending,批准则执行。"""
    import time

    item = _PENDING.pop(confirm_id, None)
    if item is None:
        return json.dumps(
            {"ok": False, "error": "确认已失效或已处理(等待超时/重复点击)"},
            ensure_ascii=False,
        )
    if time.time() - item["created_at"] > _PENDING_TTL_S:
        return json.dumps({"ok": False, "error": "确认已超时(>10 分钟),请重新发起"}, ensure_ascii=False)
    if not approved:
        return json.dumps({"ok": False, "cancelled": True, "message": "用户已取消该写操作"}, ensure_ascii=False)
    # 批准:走完整安全链(白名单+SSRF)后执行
    args = item["args"]
    ok, reason = _allowlisted(str(args.get("url") or ""))
    if not ok:
        return json.dumps({"ok": False, "error": reason}, ensure_ascii=False)
    return await run(args | {"__skip_gate__": True})


def pending_digest(confirm_id: str) -> str | None:
    return (_PENDING.get(confirm_id) or {}).get("digest")
