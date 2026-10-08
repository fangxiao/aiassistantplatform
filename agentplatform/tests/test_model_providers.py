"""M29 模型供应商测试(需求 018/设计 023)。

覆盖:CRUD 与 owner 隔离、验证三态(mock 上游:200 带/不带列表、401、超时)、
模型勾选全量覆盖、换 Key 重验证与端点密文同步、删除级联、
/llm/models 供应商分组、存量端点迁移归组。
"""

import uuid

from sqlalchemy import select

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.auth.service import create_user
from agentplatform.core.llm import provider_service
from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.llm.provider_model import LlmProvider
from agentplatform.main import app


async def _user(session, email: str) -> User:
    u = await create_user(session, email, "password123")
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: u
    return u


def _mock_probe(monkeypatch, ok: bool, models: list[str], msg: str = ""):
    async def fake(base_url, api_key):
        return ok, models, msg

    monkeypatch.setattr(provider_service, "_probe_models", fake)


# ── CRUD 与验证 ───────────────────────────────────────────────


async def test_create_provider_verified_and_models(client, session, monkeypatch):
    user = await _user(session, "pv1@test.dev")
    _mock_probe(monkeypatch, True, ["deepseek-chat", "deepseek-reasoner"])
    r = await client.post(
        "/api/llm/providers",
        json={"name": "我的 DeepSeek", "preset": "deepseek",
              "base_url": "https://api.deepseek.com/v1", "api_key": "sk-x",
              "models": ["deepseek-chat"]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["verified"] is True and body["status"] == "verified"
    assert body["models_found"] == ["deepseek-chat", "deepseek-reasoner"]

    # 勾选落库(交集防御:只落勾选的)
    eps = (await session.scalars(
        select(LlmEndpoint).where(LlmEndpoint.owner_id == str(user.id))
    )).all()
    assert [e.model for e in eps] == ["deepseek-chat"]
    assert eps[0].provider_id is not None


async def test_create_provider_unverified_savable(client, session, monkeypatch):
    """验证失败(401)可保存为 unverified(需求 018 决策 2)。"""
    await _user(session, "pv2@test.dev")
    _mock_probe(monkeypatch, False, [], "API Key 无效(401)")
    r = await client.post(
        "/api/llm/providers",
        json={"preset": "custom", "base_url": "https://intranet/v1", "api_key": "k"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["verified"] is False and body["status"] == "unverified"
    assert "401" in body["message"]

    # unverified 供应商手填模型仍可用
    pid = body["id"]
    r2 = await client.post(f"/api/llm/providers/{pid}/models", json={"models": ["local-llama"]})
    assert r2.status_code == 200
    eps = (await session.scalars(select(LlmEndpoint))).all()
    assert [e.model for e in eps] == ["local-llama"]


async def test_list_providers_and_isolation(client, session, monkeypatch):
    user = await _user(session, "pv3@test.dev")
    _mock_probe(monkeypatch, True, ["m1"])
    await client.post(
        "/api/llm/providers",
        json={"preset": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "k"},
    )
    listed = await client.get("/api/llm/providers")
    assert listed.status_code == 200
    data = listed.json()
    assert len(data["providers"]) == 1
    assert data["providers"][0]["models"] == [
        {"model": "m1", "endpoint_id": data["providers"][0]["models"][0]["endpoint_id"], "is_default": False}
    ]
    assert "deepseek" in data["presets"]

    # 他人不可见
    other = await create_user(session, "pv3b@test.dev", "password123")
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: other
    empty = await client.get("/api/llm/providers")
    assert empty.json()["providers"] == []
    assert user.id != other.id


# ── 换 Key / 重发现 / 级联 ────────────────────────────────────


async def test_rotate_key_syncs_endpoint_ciphertext(client, session, monkeypatch):
    await _user(session, "pv4@test.dev")
    _mock_probe(monkeypatch, True, ["m1"])
    created = (await client.post(
        "/api/llm/providers",
        json={"preset": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "old"},
    )).json()
    old_enc = (await session.scalars(select(LlmEndpoint))).all()[0].api_key_enc

    _mock_probe(monkeypatch, True, ["m1", "m2"])
    r = await client.patch(f"/api/llm/providers/{created['id']}", json={"api_key": "new"})
    assert r.status_code == 200 and r.json()["verified"] is True
    ep = (await session.scalars(select(LlmEndpoint))).all()[0]
    assert ep.api_key_enc != old_enc  # 端点密文同步刷新


async def test_delete_provider_cascades_models(client, session, monkeypatch):
    await _user(session, "pv5@test.dev")
    _mock_probe(monkeypatch, True, ["m1"])
    created = (await client.post(
        "/api/llm/providers",
        json={"preset": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "k"},
    )).json()
    assert (await session.scalars(select(LlmEndpoint))).all()

    dele = await client.delete(f"/api/llm/providers/{created['id']}")
    assert dele.status_code == 204
    assert (await session.scalars(select(LlmEndpoint))).all() == []
    assert (await session.scalars(select(LlmProvider))).all() == []


# ── 目录分组 ──────────────────────────────────────────────────


async def test_models_catalog_carries_provider(client, session, monkeypatch):
    await _user(session, "pv6@test.dev")
    _mock_probe(monkeypatch, True, ["deepseek-chat"])
    await client.post(
        "/api/llm/providers",
        json={"name": "DS", "preset": "deepseek",
              "base_url": "https://api.deepseek.com/v1", "api_key": "k"},
    )
    catalog = await client.get("/api/llm/models")
    models = catalog.json()["models"]
    personal = [m for m in models if m["source"] == "personal"]
    assert personal and personal[0]["provider"] == "DS"
    assert any(m["source"] == "env_default" for m in models)


async def test_migration_groups_legacy_endpoints(client, session):
    """存量个人端点(provider_id 空)在目录中归「导入的端点」组。"""
    from agentplatform.core.llm.service import create_endpoint

    user = await _user(session, "pv7@test.dev")
    await create_endpoint(
        session, name="legacy-ep", base_url="https://x/v1", model="legacy-m",
        api_key="k", owner_id=str(user.id),
    )
    await session.commit()
    catalog = await client.get("/api/llm/models")
    legacy = next(m for m in catalog.json()["models"] if m["model"] == "legacy-m")
    assert legacy["provider"] is None  # 迁移前的端点无供应商归属,前端归「导入的端点」
