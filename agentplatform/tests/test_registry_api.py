"""注册表 API 测试(设计 005 §6)。

client fixture 由 conftest 提供(get_session 依赖覆盖为测试库会话);
本模块额外先 seed 内置资源,使列表接口有数据可查。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.service import seed_builtin


@pytest.fixture
async def seeded_client(client: AsyncClient, session: AsyncSession):
    await seed_builtin(session)
    yield client


class TestListEndpoints:
    async def test_list_skills(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/skills")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        assert ids == {"skill:summarize", "skill:structured_output", "skill:cross_document_compare"}

    async def test_list_tools(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/tools")
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()}
        # M14 新增 workbench_todo;M15 P1 新增 web_search/memory
        assert ids == {
            "tool:http_request",
            "tool:web_search",
            "tool:memory",
            "tool:workbench_todo",
            "tool:pdf_parse",
            "tool:html_cleaner",
            "tool:kb_search",
            "tool:browser_action",
            "tool:browser_list_tabs",
            "tool:browser_extract_dom",
            "tool:browser_wechat_draft",
        }

    async def test_list_includes_schema_and_source(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/skills")
        first = resp.json()[0]
        assert "schema" in first
        assert first["source"] == "builtin"


class TestGetResource:
    async def test_get_latest(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/tool/pdf_parse")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "tool:pdf_parse"
        assert body["version"] == "1.0.0"
        assert "schema" in body

    async def test_get_with_constraint(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/skill/summarize", params={"version": "^1.0"})
        assert resp.status_code == 200
        assert resp.json()["version"] == "1.0.0"

    async def test_get_missing_returns_error_envelope(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/tool/nope")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "not_found"
        assert "nope" in body["error"]["message"]

    async def test_invalid_kind_returns_422(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.get("/api/registry/bogus/pdf_parse")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"
