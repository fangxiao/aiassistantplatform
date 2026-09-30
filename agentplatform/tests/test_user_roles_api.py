"""用户体系与角色权限测试(015 §8 / ADR 0008,M20)。

覆盖五要点:层级制、迁移回归(developer 门槛拆分)、审批闭环、
bootstrap 幂等、/a/{token} 入口约束。
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user, get_optional_current_user
from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import authenticate, create_user
from agentplatform.core.plugin.loader import deploy_plugin
from agentplatform.core.plugin.manifest import PluginManifest
from agentplatform.main import app


@pytest.fixture(autouse=True)
def _review_required(monkeypatch):
    """本文件测试审批制(ADR 0008)行为:恢复 plugin_review_required=True
    (20260930 起试用默认免审,生产语义仍需守护)。"""
    monkeypatch.setattr("agentplatform.config.settings.plugin_review_required", True)


pytestmark = pytest.mark.asyncio


def _act_as(client: AsyncClient, user) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_current_user] = lambda: user


@pytest.fixture
async def admin_user(session: AsyncSession):
    return await create_user(session, f"admin-{uuid.uuid4()}@t.dev", "p", UserRole.admin)


@pytest.fixture
async def dev_user(session: AsyncSession):
    return await create_user(session, f"dev-{uuid.uuid4()}@t.dev", "p", UserRole.developer)


@pytest.fixture
async def normal_user(session: AsyncSession):
    return await create_user(session, f"u-{uuid.uuid4()}@t.dev", "p", UserRole.user)


MANIFEST = {
    "name": "role-test-assistant",
    "version": "0.1.0",
    "description": "角色测试助手",
    "model": "m",
    "depends_on": [],
    "skills": [],
    "tools": [],
}


class TestHierarchy:
    """层级制:admin 通过 developer 门槛;user 被拒;门槛拆分正确。"""

    async def test_admin_passes_developer_gate(self, session, client, admin_user):
        _act_as(client, admin_user)
        r = await client.post("/api/plugins/deploy", json=MANIFEST)
        assert r.status_code == 201, r.text
        assert r.json()["review_status"] == "pending_review"
        assert r.json()["owner_id"] == str(admin_user.id)

    async def test_user_rejected_by_developer_gate(self, session, client, normal_user):
        _act_as(client, normal_user)
        r = await client.post("/api/plugins/deploy", json=MANIFEST)
        assert r.status_code == 403

    async def test_platform_management_is_admin_only(self, session, client, dev_user, normal_user):
        for who in (dev_user, normal_user):
            _act_as(client, who)
            assert (await client.get("/api/admin/llm-endpoints")).status_code == 403
            assert (await client.get("/api/insights/admin/overview")).status_code == 403
            assert (await client.get("/api/insights/admin/users")).status_code == 403
        _act_as(client, dev_user)
        # developer 保留插件域:平台端点 403 但插件管理列表 200(仅自己)
        assert (await client.get("/api/plugins")).status_code == 200

    async def test_developer_sees_only_own_plugins(self, session, client, admin_user, dev_user):
        _act_as(client, admin_user)
        assert (await client.post("/api/plugins/deploy", json=MANIFEST)).status_code == 201
        _act_as(client, dev_user)
        rows = (await client.get("/api/plugins")).json()
        assert all(p["owner_id"] == str(dev_user.id) for p in rows)

    async def test_user_management_admin_only(self, session, client, admin_user, dev_user, normal_user):
        _act_as(client, dev_user)
        assert (await client.get("/api/admin/users")).status_code == 403
        _act_as(client, admin_user)
        rows = await client.get("/api/admin/users", params={"q": "role-test"})
        assert rows.status_code == 200
        # 改角色 + 防自锁
        r = await client.patch(
            f"/api/admin/users/{normal_user.id}", json={"role": "developer"}
        )
        assert r.status_code == 200 and r.json()["role"] == "developer"
        assert (await client.patch(f"/api/admin/users/{admin_user.id}", json={"role": "user"})).status_code == 422
        # 禁用后登录拒绝
        r = await client.patch(f"/api/admin/users/{normal_user.id}", json={"disabled": True})
        assert r.status_code == 200 and r.json()["disabled"] is True
        assert await authenticate(session, normal_user.email, "p") is None


class TestReviewFlow:
    """审批闭环:deploy 待审 → 不可见 → approve → 可见 → 重部署退回待审。"""

    async def test_deploy_approve_visibility_cycle(self, session, client, dev_user, normal_user):
        _act_as(client, dev_user)
        r = await client.post("/api/plugins/deploy", json=MANIFEST)
        assert r.status_code == 201, r.text
        pid = r.json()["id"]

        # 未过审:普通用户广场不可见、详情 404、建会话 404
        _act_as(client, normal_user)
        assert all(a["id"] != pid for a in (await client.get("/api/assistants")).json())
        assert (await client.get(f"/api/assistants/{pid}")).status_code == 404

        # owner 自己可见(带待审标记)
        _act_as(client, dev_user)
        assert any(a["id"] == pid for a in (await client.get("/api/assistants")).json())

        # developer 不能审批
        assert (await client.post(f"/api/plugins/{pid}/review", json={"action": "approve"})).status_code == 403

        # admin approve → 普通用户可见
        admin = await create_user(session, f"a2-{uuid.uuid4()}@t.dev", "p", UserRole.admin)
        _act_as(client, admin)
        r = await client.post(f"/api/plugins/{pid}/review", json={"action": "approve"})
        assert r.status_code == 200 and r.json()["review_status"] == "approved"

        _act_as(client, normal_user)
        assert any(a["id"] == pid for a in (await client.get("/api/assistants")).json())

        # 同名重部署 → 退回 pending_review,普通用户又不可见
        _act_as(client, dev_user)
        r = await client.post("/api/plugins/deploy", json=MANIFEST)
        assert r.status_code == 201 and r.json()["review_status"] == "pending_review"
        _act_as(client, normal_user)
        assert all(a["id"] != pid for a in (await client.get("/api/assistants")).json())

    async def test_reject_resubmit_cycle(self, session, client, dev_user, admin_user):
        _act_as(client, dev_user)
        pid = (await client.post("/api/plugins/deploy", json=MANIFEST)).json()["id"]

        # reject 必填原因
        _act_as(client, admin_user)
        assert (
            await client.post(f"/api/plugins/{pid}/review", json={"action": "reject"})
        ).status_code == 422
        r = await client.post(
            f"/api/plugins/{pid}/review", json={"action": "reject", "reason": "提示词不符合规范"}
        )
        assert r.status_code == 200 and r.json()["review_status"] == "rejected"
        assert r.json()["last_review_reason"] == "提示词不符合规范"

        # owner 重提 → pending,原因清空
        _act_as(client, dev_user)
        r = await client.post(f"/api/plugins/{pid}/resubmit")
        assert r.status_code == 200 and r.json()["review_status"] == "pending_review"
        assert r.json()["last_review_reason"] is None
        # 非驳回态不可重提
        _act_as(client, admin_user)
        assert (await client.post(f"/api/plugins/{pid}/resubmit")).status_code == 422

    async def test_enable_is_admin_disable_owner_allowed(self, session, client, dev_user, admin_user):
        _act_as(client, dev_user)
        pid = (await client.post("/api/plugins/deploy", json=MANIFEST)).json()["id"]
        assert (await client.post(f"/api/plugins/{pid}/enable")).status_code == 403  # 启用仅 admin
        _act_as(client, admin_user)
        assert (await client.post(f"/api/plugins/{pid}/enable")).status_code == 200
        _act_as(client, dev_user)
        # owner 可下架自己的
        assert (await client.post(f"/api/plugins/{pid}/disable")).status_code == 200
        # 他人插件 developer 不可见不可操作
        _act_as(client, admin_user)
        pid2 = (
            await client.post("/api/plugins/deploy", json={**MANIFEST, "name": "role-test-2"})
        ).json()["id"]
        _act_as(client, dev_user)
        assert (await client.post(f"/api/plugins/{pid2}/disable")).status_code == 404
        assert (await client.delete(f"/api/plugins/{pid2}")).status_code == 404


class TestTokenEntry:
    """/a/{token} 审批约束:未过审 owner/admin 可入,其余 404;join 仅过审开放。"""

    async def test_unapproved_token_gating(self, session, client, dev_user, admin_user, normal_user):
        _act_as(client, dev_user)
        pid = (await client.post("/api/plugins/deploy", json=MANIFEST)).json()["id"]
        token = (await client.post(f"/api/assistant-access/plugins/{pid}/publish")).json()["access_token"]

        # 未过审:匿名/普通用户 404;owner/admin 可预览
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides[get_optional_current_user] = lambda: None
        assert (await client.get(f"/api/assistant-access/{token}")).status_code == 404
        _act_as(client, normal_user)
        assert (await client.get(f"/api/assistant-access/{token}")).status_code == 404
        assert (await client.post(f"/api/assistant-access/{token}/join", json={"nickname": "n"})).status_code == 404
        _act_as(client, dev_user)
        assert (await client.get(f"/api/assistant-access/{token}")).status_code == 200

        # approve 后 join 开放
        _act_as(client, admin_user)
        assert (await client.post(f"/api/plugins/{pid}/review", json={"action": "approve"})).status_code == 200
        app.dependency_overrides[get_optional_current_user] = lambda: None
        r = await client.post(f"/api/assistant-access/{token}/join", json={"nickname": "访客"})
        assert r.status_code == 200 and r.json()["user"]["nickname"] == "访客"

    async def test_stats_owner_only(self, session, client, dev_user, normal_user):
        _act_as(client, dev_user)
        pid = (await client.post("/api/plugins/deploy", json=MANIFEST)).json()["id"]
        _act_as(client, normal_user)
        assert (await client.get(f"/api/assistant-access/plugins/{pid}/stats")).status_code == 404


class TestBootstrap:
    """ensure_initial_admin:升级/创建/幂等/未配置跳过。"""

    async def test_promote_and_create_and_idempotent(self, session, monkeypatch):
        from agentplatform.core.auth.service import ensure_initial_admin

        monkeypatch.setattr("agentplatform.config.settings.initial_admin_email", "boss@x.dev")
        monkeypatch.setattr("agentplatform.config.settings.initial_admin_password", "secret123")

        # 既有用户升级
        existing = await create_user(session, "boss@x.dev", "p", UserRole.user)
        await ensure_initial_admin(session)
        await session.commit()
        await session.refresh(existing)
        assert existing.role == UserRole.admin

        # 不存在则创建;重复启动幂等
        for _ in range(2):
            await ensure_initial_admin(session)
        await session.commit()
        created = await authenticate(session, "boss@x.dev", "p")
        assert created is not None and created.role == UserRole.admin

    async def test_noop_without_config(self, session, monkeypatch):
        from agentplatform.core.auth.service import ensure_initial_admin

        monkeypatch.setattr("agentplatform.config.settings.initial_admin_email", "")
        await ensure_initial_admin(session)  # 不抛异常即通过
