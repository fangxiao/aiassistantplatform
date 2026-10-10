"""M33:邮箱强制验证闸门(20261010 家庭场景反馈:gmail 未验证也能登录)。

覆盖:域名白名单 / SMTP 未配 fail-fast / 未验证登录 403+自动补发 /
验证后登录 200 / admin 手动标记救急 / 开关关闭时全放行。
"""

import pytest

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.service import create_user
from agentplatform.main import app


async def _setup(client, session, email="gate@test.dev", enable=True):
    """开关 + 干净账号;返回账号。"""
    from agentplatform.config import settings

    settings.email_verification_required = enable
    settings.notify_smtp_host = "smtp.test" if enable else ""
    user = await create_user(session, email, "password123")
    await session.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    return user


@pytest.fixture(autouse=True)
def _restore():
    from agentplatform.config import settings

    yield
    settings.email_verification_required = False
    settings.notify_smtp_host = ""


async def test_register_domain_whitelist(client, session):
    """不支持的服务商(如随机企业域)注册 422;gmail 放行。"""
    from agentplatform.config import settings

    settings.email_verification_required = True
    settings.notify_smtp_host = "smtp.test"
    r = await client.post(
        "/api/auth/register",
        json={"email": "someone@random-corp.xyz", "password": "password123"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "email_domain_unsupported"
    settings.email_verification_required = False
    r2 = await client.post(
        "/api/auth/register",
        json={"email": "someone@gmail.com", "password": "password123"},
    )
    assert r2.status_code == 201
    # 开关关闭时任意域名放行(验证不强制则无送达性诉求)
    r3 = await client.post(
        "/api/auth/register",
        json={"email": "any@random-corp.xyz", "password": "password123"},
    )
    assert r3.status_code == 201


async def test_register_fails_fast_without_smtp(client, session):
    """强制验证 + SMTP 未配 → 注册 503(避免制造永远无法验证的死锁账号)。"""
    from agentplatform.config import settings

    settings.email_verification_required = True
    settings.notify_smtp_host = ""
    r = await client.post(
        "/api/auth/register",
        json={"email": "x@qq.com", "password": "password123"},
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "smtp_not_configured"


async def test_login_blocked_until_verified(client, session, monkeypatch):
    """未验证登录 403(带补发);验证后 200。"""
    user = await _setup(client, session, "unverified@test.dev")
    sent = []
    from agentplatform.api import auth as auth_api

    monkeypatch.setattr(auth_api, "_send_verification_email_bg", lambda uid, em, web_base="": sent.append(em))

    r = await client.post("/api/auth/login", json={"email": "unverified@test.dev", "password": "password123"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_unverified"
    assert sent, "被拦时应自动补发一封"

    from datetime import UTC, datetime

    user.email_verified_at = datetime.now(UTC)
    await session.commit()
    r2 = await client.post("/api/auth/login", json={"email": "unverified@test.dev", "password": "password123"})
    assert r2.status_code == 200


async def test_gate_off_allows_unverified(client, session):
    """开关关闭(E2E/私有化可选)→ 未验证照常登录。"""
    user = await _setup(client, session, "off@test.dev", enable=False)
    assert user.email_verified_at is None
    r = await client.post("/api/auth/login", json={"email": "off@test.dev", "password": "password123"})
    assert r.status_code == 200


async def test_admin_manual_verify(client, session):
    """admin 手动标记已验证(收不到邮件的救急通道)。"""
    from agentplatform.core.auth.model import UserRole
    from sqlalchemy import select

    user = await _setup(client, session, "rescue@test.dev")
    admin = await create_user(session, "root@test.dev", "password123", UserRole.admin)
    await session.commit()
    from agentplatform.core.auth.model import User as _U

    admin2 = await session.scalar(select(_U).where(_U.email == "root@test.dev"))
    app.dependency_overrides[get_current_user] = lambda: admin2

    r = await client.patch(
        f"/api/admin/users/{user.id}",
        json={"email_verified": True},
    )
    assert r.status_code == 200, r.text
    await session.refresh(user)
    assert user.email_verified_at is not None
