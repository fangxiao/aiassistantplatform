"""注册表 API 测试(设计 005 §6)。

用 httpx.AsyncClient + ASGITransport 在同一事件循环跑 ASGI 应用,
并覆盖 get_session 依赖注入测试库会话,避免 TestClient 的跨循环问题。
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.db.session import get_session
from agentplatform.core.registry.service import seed_builtin
from agentplatform.main import app


@pytest.fixture
async def client(session: AsyncSession):
    await seed_builtin(session)
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestListEndpoints:
    async def test_list_skills(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/skills")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        assert ids == {"skill:summarize", "skill:structured_output"}

    async def test_list_tools(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/tools")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        assert ids == {"tool:pdf_parse"}

    async def test_list_includes_schema_and_source(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/skills")
        first = resp.json()[0]
        assert "schema" in first
        assert first["source"] == "builtin"


class TestGetResource:
    async def test_get_latest(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/tool/pdf_parse")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "tool:pdf_parse"
        assert body["version"] == "1.0.0"
        assert "schema" in body

    async def test_get_with_constraint(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/skill/summarize", params={"version": "^1.0"})
        assert resp.status_code == 200
        assert resp.json()["version"] == "1.0.0"

    async def test_get_missing_returns_error_envelope(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/tool/nope")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "not_found"
        assert "nope" in body["error"]["message"]

    async def test_invalid_kind_returns_422(self, client: AsyncClient) -> None:
        resp = await client.get("/api/registry/bogus/pdf_parse")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"
