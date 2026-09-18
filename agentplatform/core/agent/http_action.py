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
