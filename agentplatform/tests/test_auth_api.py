"""认证 API 测试(设计 005 §2)。

这里不使用 conftest 的 client fixture(它覆盖了 get_current_user 固定身份),
改为 raw_client —— 只覆盖 get_session,让真实 JWT 路径生效,从而验证:
401 无令牌 / 401 错误凭据 / 注册 / 登录 / me。
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.db.session import get_session
from agentplatform.main import app


@pytest.fixture
async def raw_client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """仅覆盖 DB 会话、不干预鉴权的客户端(鉴权走真实 JWT)。"""
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


REGISTER = {"email": "alice@test.dev", "password": "password123"}
LOGIN = {"email": "alice@test.dev", "password": "password123"}


class TestRegister:
    async def test_register_returns_user(self, raw_client: AsyncClient) -> None:
        resp = await raw_client.post("/api/auth/register", json=REGISTER)
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "alice@test.dev"
        assert "password_hash" not in body
        assert "password" not in body
        assert body["role"] == "user"

    async def test_register_duplicate_email_409(self, raw_client: AsyncClient) -> None:
        await raw_client.post("/api/auth/register", json=REGISTER)
        resp = await raw_client.post("/api/auth/register", json=REGISTER)
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "email_exists"

    async def test_register_short_password_422(self, raw_client: AsyncClient) -> None:
        bad = {**REGISTER, "password": "123"}
        resp = await raw_client.post("/api/auth/register", json=bad)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"


class TestLogin:
    async def test_login_success(self, raw_client: AsyncClient) -> None:
        await raw_client.post("/api/auth/register", json=REGISTER)
        resp = await raw_client.post("/api/auth/login", json=LOGIN)
        assert resp.status_code == 200
        body = resp.json()
        assert body["token"]
        assert body["user"]["email"] == "alice@test.dev"

    async def test_login_wrong_password_401(self, raw_client: AsyncClient) -> None:
        await raw_client.post("/api/auth/register", json=REGISTER)
        resp = await raw_client.post(
            "/api/auth/login", json={**LOGIN, "password": "wrongpass"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"

    async def test_login_unknown_email_401(self, raw_client: AsyncClient) -> None:
        resp = await raw_client.post("/api/auth/login", json=LOGIN)
        assert resp.status_code == 401


class TestMe:
    async def test_me_with_token(self, raw_client: AsyncClient) -> None:
        await raw_client.post("/api/auth/register", json=REGISTER)
        token = (await raw_client.post("/api/auth/login", json=LOGIN)).json()["token"]
        resp = await raw_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "alice@test.dev"

    async def test_me_without_token_401(self, raw_client: AsyncClient) -> None:
        resp = await raw_client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"

    async def test_me_bad_token_401(self, raw_client: AsyncClient) -> None:
        resp = await raw_client.get(
            "/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
        )
        assert resp.status_code == 401


class TestProtectedEndpoints:
    async def test_business_api_without_token_401(
        self, raw_client: AsyncClient
    ) -> None:
        resp = await raw_client.get("/api/registry/skills")
        assert resp.status_code == 401

    async def test_business_api_with_valid_token_200(
        self, raw_client: AsyncClient
    ) -> None:
        await raw_client.post("/api/auth/register", json=REGISTER)
        token = (await raw_client.post("/api/auth/login", json=LOGIN)).json()["token"]
        resp = await raw_client.get(
            "/api/registry/skills", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200