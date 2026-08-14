"""插件部署与管理 API 测试(设计 005 §5)。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.service import seed_builtin

MANIFEST = {
    "name": "prd-review-assistant",
    "version": "0.1.0",
    "description": "PRD 文档评审助手",
    "model": "glm-5.2",
    "depends_on": ["tool:pdf_parse@^1.0", "skill:summarize@^1.0"],
    "skills": [
        {
            "id": "skill:prd_review",
            "file": "./skills/prd_review.py",
            "schema": {"parameters": {"type": "object"}},
        }
    ],
    "tools": [],
}


@pytest.fixture
async def seeded_client(client: AsyncClient, session: AsyncSession):
    await seed_builtin(session)
    yield client


class TestDeploy:
    async def test_deploy_success(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.post("/api/plugins/deploy", json=MANIFEST)
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "prd-review-assistant"
        assert body["version"] == "0.1.0"
        assert body["status"] == "active"
        assert body["model"] == "glm-5.2"

    async def test_deploy_missing_dependency_422(self, seeded_client: AsyncClient) -> None:
        bad = {**MANIFEST, "depends_on": ["skill:missing@^1.0"]}
        resp = await seeded_client.post("/api/plugins/deploy", json=bad)
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "dependency_missing"
        assert "missing" in body["error"]["message"]

    async def test_deploy_invalid_manifest_422(self, seeded_client: AsyncClient) -> None:
        bad = {**MANIFEST, "version": "not-a-semver"}
        resp = await seeded_client.post("/api/plugins/deploy", json=bad)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "plugin_invalid"

    async def test_deploy_duplicate_422(self, seeded_client: AsyncClient) -> None:
        await seeded_client.post("/api/plugins/deploy", json=MANIFEST)
        resp = await seeded_client.post("/api/plugins/deploy", json=MANIFEST)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "plugin_invalid"


class TestManage:
    async def test_list(self, seeded_client: AsyncClient) -> None:
        await seeded_client.post("/api/plugins/deploy", json=MANIFEST)
        resp = await seeded_client.get("/api/plugins")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_disable_enable(self, seeded_client: AsyncClient) -> None:
        pid = (await seeded_client.post("/api/plugins/deploy", json=MANIFEST)).json()["id"]
        resp = await seeded_client.post(f"/api/plugins/{pid}/disable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"
        resp = await seeded_client.post(f"/api/plugins/{pid}/enable")
        assert resp.json()["status"] == "active"

    async def test_uninstall_removes_resources(self, seeded_client: AsyncClient) -> None:
        pid = (await seeded_client.post("/api/plugins/deploy", json=MANIFEST)).json()["id"]
        resp = await seeded_client.delete(f"/api/plugins/{pid}")
        assert resp.status_code == 204
        # 私有资源已从注册表移除
        skills = await seeded_client.get("/api/registry/skills")
        ids = {r["id"] for r in skills.json()}
        assert "skill:prd_review" not in ids

    async def test_manage_missing_404(self, seeded_client: AsyncClient) -> None:
        resp = await seeded_client.post("/api/plugins/00000000-0000-0000-0000-000000000000/disable")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"
