"""LLM 端点测试:crypto 加密往返、服务 CRUD/默认切换、管理 API。"""

import uuid

import pytest
from cryptography.fernet import InvalidToken
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentplatform.core.llm import crypto
from agentplatform.core.llm.schemas import LlmEndpointCreate
from agentplatform.core.llm.service import (
    create_endpoint,
    get_api_key,
    get_endpoint,
    list_endpoints,
    update_endpoint,
)

ENDPOINT = LlmEndpointCreate(
    name="glm-5.2",
    base_url="https://api.example.com/v1",
    model="glm-5.2",
    api_key="sk-test-secret",
)


class TestCrypto:
    def test_roundtrip(self) -> None:
        token = crypto.encrypt("sk-secret")
        assert token != "sk-secret"
        assert crypto.decrypt(token) == "sk-secret"

    def test_decrypt_with_wrong_key_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        token = crypto.encrypt("sk-secret")
        monkeypatch.setattr(crypto.settings, "secret_key", "other-secret")
        with pytest.raises(InvalidToken):
            crypto.decrypt(token)


class TestEndpointService:
    async def test_create_and_get(self, session: AsyncSession) -> None:
        endpoint = await create_endpoint(session, **ENDPOINT.model_dump())
        await session.commit()
        assert endpoint.api_key_enc != "sk-test-secret"  # 加密存储
        fetched = await get_endpoint(session, endpoint.id)
        assert fetched is not None
        assert get_api_key(fetched) == "sk-test-secret"  # 服务层可取明文

    async def test_list(self, session: AsyncSession) -> None:
        await create_endpoint(session, **ENDPOINT.model_dump())
        await create_endpoint(session, name="deepseek", base_url="https://b", model="deepseek", api_key="k2")
        await session.commit()
        names = [e.name for e in await list_endpoints(session)]
        assert names == ["deepseek", "glm-5.2"]

    async def test_update_fields(self, session: AsyncSession) -> None:
        ep = await create_endpoint(session, **ENDPOINT.model_dump())
        updated = await update_endpoint(session, ep.id, model="glm-5.2-plus", api_key="sk-new")
        await session.commit()
        assert updated is not None
        assert updated.model == "glm-5.2-plus"
        assert get_api_key(updated) == "sk-new"

    async def test_update_missing_returns_none(self, session: AsyncSession) -> None:
        assert await update_endpoint(session, uuid.uuid4(), name="x") is None

    async def test_set_default_clears_others(self, session: AsyncSession) -> None:
        a = await create_endpoint(session, **ENDPOINT.model_dump())
        b = await create_endpoint(session, name="deepseek", base_url="https://b", model="deepseek", api_key="k2", is_default=True)
        await session.commit()
        a_row = await get_endpoint(session, a.id)
        b_row = await get_endpoint(session, b.id)
        assert a_row is not None and b_row is not None
        assert a_row.is_default is False
        assert b_row.is_default is True
        await update_endpoint(session, a.id, is_default=True)
        await session.commit()
        a_row2 = await get_endpoint(session, a.id)
        b_row2 = await get_endpoint(session, b.id)
        assert a_row2 is not None and b_row2 is not None
        assert a_row2.is_default is True
        assert b_row2.is_default is False


class TestEndpointApi:
    async def test_create_and_list(self, client: AsyncClient) -> None:
        resp = await client.post("/api/admin/llm-endpoints", json=ENDPOINT.model_dump())
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "glm-5.2"
        assert "api_key" not in body  # 响应不回明文
        assert "api_key_enc" not in body

        resp2 = await client.get("/api/admin/llm-endpoints")
        assert resp2.status_code == 200
        assert len(resp2.json()) == 1

    async def test_patch(self, client: AsyncClient) -> None:
        created = (await client.post("/api/admin/llm-endpoints", json=ENDPOINT.model_dump())).json()
        resp = await client.patch(
            f"/api/admin/llm-endpoints/{created['id']}",
            json={"model": "glm-5.2-plus", "is_default": True},
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "glm-5.2-plus"
        assert resp.json()["is_default"] is True

    async def test_patch_missing_404(self, client: AsyncClient) -> None:
        resp = await client.patch(f"/api/admin/llm-endpoints/{uuid.uuid4()}", json={"name": "x"})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    async def test_create_persists_across_sessions(
        self, client: AsyncClient, db_engine, session: AsyncSession
    ) -> None:
        """回归:M3 曾缺 commit,同一请求内可见但新会话查不到。"""
        resp = await client.post("/api/admin/llm-endpoints", json=ENDPOINT.model_dump())
        assert resp.status_code == 201
        factory = async_sessionmaker(db_engine, expire_on_commit=False)
        async with factory() as fresh:
            rows = await list_endpoints(fresh)
            assert len(rows) == 1
