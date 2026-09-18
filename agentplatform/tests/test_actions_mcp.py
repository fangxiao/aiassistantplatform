"""M17 测试:http_request 白名单/SSRF、MCP 握手/工具/鉴权。"""

import json
import uuid

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.agent.http_action import run as run_http_action
from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KbVisibility


@pytest.fixture
async def dev_user(session: AsyncSession):
    return await create_user(session, f'mcp-{uuid.uuid4()}@test.dev', 'password123', UserRole.developer)


class TestHttpRequestTool:
    async def test_disabled_when_allowlist_empty(self, monkeypatch) -> None:
        """安全默认:白名单空 = 工具禁用(明确提示,非崩溃)。"""
        monkeypatch.setattr(settings, "action_http_allowlist", [])
        out = json.loads(await run_http_action({"method": "GET", "url": "https://example.com/x"}))
        assert out["ok"] is False and "ACTION_HTTP_ALLOWLIST" in out["error"]

    async def test_allowlist_domain_executes(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        monkeypatch.setattr(settings, "action_require_confirm", False)  # 闸门单测另行覆盖

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "sent"})

        out = json.loads(await _run_with_transport(
            {"method": "POST", "url": "https://example.com/send", "body": "{\"msg\":\"hi\"}"},
            handler,
        ))
        assert out["ok"] is True and out["status"] == 200

    async def test_non_allowlisted_rejected(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        out = json.loads(await run_http_action({"method": "GET", "url": "https://evil.example.com/x"}))
        assert out["ok"] is False and "白名单" in out["error"]

    async def test_ssrf_internal_blocked(self, monkeypatch) -> None:
        """白名单内的域名解析到内网地址同样拦截(DNS 级)。"""
        monkeypatch.setattr(settings, "action_http_allowlist", ["internal.example.com"])
        from agentplatform.core.kb.connectors import web as web_module

        async def fake_resolve(host: str) -> list[str]:
            return ["10.0.0.5"]  # 内网

        monkeypatch.setattr(web_module, "_resolve_host", fake_resolve)
        out = json.loads(await run_http_action({"method": "GET", "url": "https://internal.example.com/admin"}))
        assert out["ok"] is False and "受限" in out["error"]


async def _run_with_transport(args: dict, handler) -> str:
    import agentplatform.core.agent.http_action as ha

    transport = httpx.MockTransport(handler)
    real_client = ha.httpx.AsyncClient

    class _Client(real_client):
        def __init__(self, **kw):
            kw["transport"] = transport
            super().__init__(**kw)

    ha.httpx.AsyncClient = _Client
    try:
        return await ha.run(args)
    finally:
        ha.httpx.AsyncClient = real_client


class TestMcpServer:
    async def _rpc(self, client: AsyncClient, payload: dict) -> dict:
        r = await client.post("/api/mcp", json=payload)
        assert r.status_code == 200
        return r.json()

    async def test_initialize_and_tools_list(self, client: AsyncClient) -> None:
        init = await self._rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert init["result"]["serverInfo"]["name"] == "agentplatform"
        listed = await self._rpc(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == {"platform_kb_search", "platform_list_kbs"}

    async def test_list_kbs_tool(self, client: AsyncClient, session: AsyncSession, dev_user) -> None:
        kb = await kb_service.create_kb(
            session, name="mcp库", slug=f"mcp{uuid.uuid4().hex[:8]}",
            owner=dev_user, visibility=KbVisibility.private,
        )
        await session.commit()
        # MCP 以 token 身份执行:切换 client 身份为 dev_user(private 库 owner)
        from agentplatform.core.auth.dependencies import get_current_user
        from agentplatform.main import app

        app.dependency_overrides[get_current_user] = lambda: dev_user
        r = await self._rpc(client, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                     "params": {"name": "platform_list_kbs", "arguments": {}}})
        text = r["result"]["content"][0]["text"]
        assert "mcp库" in text

    async def test_kb_search_tool_no_kb(self, client: AsyncClient) -> None:
        r = await self._rpc(client, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                     "params": {"name": "platform_kb_search", "arguments": {"query": "x"}}})
        assert "没有可见知识库" in r["result"]["content"][0]["text"] or "无" in r["result"]["content"][0]["text"]

    async def test_unknown_method(self, client: AsyncClient) -> None:
        r = await self._rpc(client, {"jsonrpc": "2.0", "id": 5, "method": "nope"})
        assert r["error"]["code"] == -32601


class TestWriteConfirmGate:
    """M17 P1:写操作确认闸门——LLM 无法绕过,人工确认后才执行。"""

    async def test_write_method_pends(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        monkeypatch.setattr(settings, "action_require_confirm", True)
        out = json.loads(await run_http_action({"method": "POST", "url": "https://example.com/x", "body": "{}"}))
        assert out.get("pending") is True and out.get("confirm_id")
        assert "POST https://example.com/x" in out["digest"]

    async def test_get_passes_directly(self, monkeypatch) -> None:
        """读操作不需要确认(直通执行链)。"""
        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        out = json.loads(await run_http_action({"method": "GET", "url": "https://example.com/x"}))
        assert "pending" not in out  # 走白名单/DNS 链(此处 example.com 可解析)

    async def test_confirm_executes_once(self, monkeypatch) -> None:
        from agentplatform.core.agent.http_action import confirm_and_run

        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        monkeypatch.setattr(settings, "action_require_confirm", True)
        out = json.loads(await run_http_action({"method": "POST", "url": "https://example.com/x", "body": "{}"}))
        cid = out["confirm_id"]
        # 批准 → 执行(example.com 真实可达)
        result = json.loads(await confirm_and_run(cid, True))
        # 真实请求已发出(example.com 对 POST 返回 405——执行本身成功)
        assert result.get("status") in (200, 405)
        # 一次性:再确认同一 id → 失效
        again = json.loads(await confirm_and_run(cid, True))
        assert again["ok"] is False and "失效" in again["error"]

    async def test_cancel(self, monkeypatch) -> None:
        from agentplatform.core.agent.http_action import confirm_and_run

        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        monkeypatch.setattr(settings, "action_require_confirm", True)
        out = json.loads(await run_http_action({"method": "DELETE", "url": "https://example.com/x"}))
        result = json.loads(await confirm_and_run(out["confirm_id"], False))
        assert result.get("cancelled") is True

    async def test_gate_disabled_by_config(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "action_http_allowlist", ["example.com"])
        monkeypatch.setattr(settings, "action_require_confirm", False)
        out = json.loads(await run_http_action({"method": "POST", "url": "https://example.com/x", "body": "{}"}))
        assert "pending" not in out  # 关闭闸门则直通
