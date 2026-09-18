"""MCP server(M17,设计 014 §2):平台能力经 Model Context Protocol 对外暴露。

手写最小 JSON-RPC(streamable HTTP:单 POST 端点,server 直接回 JSON 响应),
零新依赖。协议面:initialize / notifications/initialized / tools/list / tools/call。
鉴权:Bearer JWT(get_current_user)——tools/call 以该用户身份执行,
知识库检索范围 = 该用户可见库(M12 权限同源)。

Claude Code 配置示例(mcpServers):
{
  "agentplatform": {
    "type": "http",
    "url": "http://localhost:8000/api/mcp",
    "headers": {"Authorization": "Bearer <token>"}
  }
}
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KnowledgeBase
from agentplatform.core.kb.search_tool import run_kb_search

router = APIRouter(prefix="/mcp", tags=["mcp"])

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "agentplatform", "version": "0.1.0"}

TOOLS_SPEC = [
    {
        "name": "platform_kb_search",
        "description": "在 AgentPlatform 的知识库中做语义检索(仅当前用户可见的库),返回带文档名与来源的片段",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题"},
                "top_k": {"type": "integer", "description": "返回条数,默认 5"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "platform_list_kbs",
        "description": "列出当前用户可见的知识库(名称/描述/文档数)",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _rpc_result(id_, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def _rpc_error(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def _mcp_text(text: str, *, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


async def _tool_list_kbs(db: AsyncSession, user: User, args: dict) -> dict:
    rows = await kb_service.list_visible_kbs(db, str(user.id))
    lines = [
        f"- {k.name}(docs: {k.doc_count}, chunks: {k.chunk_count}, visibility: {k.visibility.value})"
        + (f" — {k.description}" if k.description else "")
        for k in rows
    ]
    return _mcp_text("\n".join(lines) or "当前用户没有可见知识库")


async def _tool_kb_search(db: AsyncSession, user: User, args: dict) -> dict:
    query = str(args.get("query") or "").strip()
    if not query:
        return _mcp_text("query 不能为空", is_error=True)
    rows = await kb_service.list_visible_kbs(db, str(user.id))
    allowed = [k.id for k in rows if k.status == "active"]
    if not allowed:
        return _mcp_text("当前用户没有可见知识库,无法检索", is_error=True)
    raw = await run_kb_search(db, allowed, {"query": query, "top_k": args.get("top_k") or 5})
    data = json.loads(raw)
    return _mcp_text(json.dumps(data, ensure_ascii=False))


@router.post("")
async def mcp_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """MCP streamable HTTP 单端点(手写最小 JSON-RPC;Bearer JWT 鉴权)。"""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid json") from exc

    if isinstance(body, list):  # batch:逐个处理(协议允许)
        results = [await _handle(msg, db, user) for msg in body if isinstance(msg, dict)]
        return [r for r in results if r is not None]
    result = await _handle(body, db, user)
    if result is None:  # notification:无响应
        from fastapi import Response

        return Response(status_code=202)
    return result


async def _handle(msg: dict, db: AsyncSession, user: User):
    method = msg.get("method", "")
    id_ = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _rpc_result(
            id_,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method.startswith("notifications/"):
        return None  # 通知无响应
    if method == "tools/list":
        return _rpc_result(id_, {"tools": TOOLS_SPEC})
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        if name == "platform_list_kbs":
            return _rpc_result(id_, await _tool_list_kbs(db, user, args))
        if name == "platform_kb_search":
            return _rpc_result(id_, await _tool_kb_search(db, user, args))
        return _rpc_error(id_, -32602, f"未知工具: {name}")
    if id_ is None:
        return None
    return _rpc_error(id_, -32601, f"未知方法: {method}")
