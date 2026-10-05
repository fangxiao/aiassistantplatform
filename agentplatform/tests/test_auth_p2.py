"""M24 P2 认证加固测试(需求 013 B1-B3/设计 018 §5-§9)。

覆盖:双令牌签发与 cookie 属性 / 轮换与重放吊销全族 / legacy JWT 兼容 /
登出 / 邮箱验证流与重发限频 / OAuth state / 飞书 mock 全链。
"""

from datetime import UTC, datetime, timedelta
from typing import ClassVar

from jose import jwt as jose_jwt
from sqlalchemy import select

from agentplatform.config import settings
from agentplatform.core.auth import tokens as tk
from agentplatform.core.auth.model import User
from agentplatform.core.auth.oauth_model import UserIdentity
from agentplatform.core.auth.service import create_user

PREFIX = "/api/auth"


async def _register(client, email: str, password: str = "password123"):
    return await client.post(f"{PREFIX}/register", json={"email": email, "password": password})


async def _login(client, email: str, password: str = "password123"):
    return await client.post(f"{PREFIX}/login", json={"email": email, "password": password})


# ── B1 双令牌 ─────────────────────────────────────────────────


async def test_login_issues_dual_tokens(client):
    reg = await _register(client, "dual@test.dev")
    assert reg.status_code == 201

    resp = await _login(client, "dual@test.dev")
    assert resp.status_code == 200
    body = resp.json()
    claims = jose_jwt.decode(body["token"], settings.secret_key, algorithms=["HS256"])
    assert claims["typ"] == "access"
    # access 2h(允许 1-3h 区间)
    exp = datetime.fromtimestamp(claims["exp"], tz=UTC)
    assert timedelta(hours=1) < exp - datetime.now(UTC) < timedelta(hours=3)
    assert body["user"]["email"] == "dual@test.dev"
    assert body["user"]["email_verified"] is False  # 密码注册默认未验证

    cookie = resp.headers.get("set-cookie", "")
    assert "rf=" in cookie and "HttpOnly" in cookie
    assert "Path=/api/auth" in cookie and "samesite=lax" in cookie.lower()
    assert "Max-Age=2592000" in cookie


async def test_refresh_rotation_then_replay_kills_family(client):
    await _register(client, "rot@test.dev")
    login = await _login(client, "rot@test.dev")
    first = login.cookies.get("rf")
    assert first and first.startswith("rf_")

    r1 = await client.post(f"{PREFIX}/refresh")
    assert r1.status_code == 200
    second = r1.cookies.get("rf")
    assert second and second != first

    # 重放已轮换令牌 → 401,且全族吊销:新令牌也随之失效
    client.cookies.set("rf", first)
    r2 = await client.post(f"{PREFIX}/refresh")
    assert r2.status_code == 401
    client.cookies.set("rf", second)
    r3 = await client.post(f"{PREFIX}/refresh")
    assert r3.status_code == 401


async def test_refresh_without_cookie_401(client):
    resp = await client.post(f"{PREFIX}/refresh")
    assert resp.status_code == 401


async def test_logout_revokes_family(client):
    await _register(client, "out@test.dev")
    await _login(client, "out@test.dev")
    await client.post(f"{PREFIX}/refresh")
    out = await client.post(f"{PREFIX}/logout")
    assert out.status_code == 200
    again = await client.post(f"{PREFIX}/refresh")
    assert again.status_code == 401


async def test_legacy_30d_jwt_still_accepted(client, session):
    """存量 30d JWT(无 typ)在有效期内继续可用(A6/B1.5 兼容)。"""
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    user = await create_user(session, "legacy@test.dev", "password123")
    await session.commit()
    app.dependency_overrides.pop(get_current_user, None)  # 还原真实鉴权

    token = tk.create_legacy_access_token(str(user.id), "user")
    resp = await client.get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "legacy@test.dev"


async def test_email_verify_token_rejected_as_bearer(client, session):
    """验证类 JWT 不能冒充 access。"""
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    user = await create_user(session, "spoof@test.dev", "password123")
    await session.commit()
    app.dependency_overrides.pop(get_current_user, None)  # 还原真实鉴权
    bad = tk.create_email_verify_token(str(user.id))
    resp = await client.get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {bad}"})
    assert resp.status_code == 401


# ── B3 邮箱验证 ────────────────────────────────────────────────


async def test_email_verify_flow_and_idempotent(client, session):
    user = await create_user(session, "verify@test.dev", "password123")
    await session.commit()
    assert user.email_verified_at is None

    token = tk.create_email_verify_token(str(user.id))
    r1 = await client.post(f"{PREFIX}/verify-email", json={"token": token})
    assert r1.status_code == 200
    await session.refresh(user)
    assert user.email_verified_at is not None

    # 幂等:重复验证仍成功
    r2 = await client.post(f"{PREFIX}/verify-email", json={"token": token})
    assert r2.status_code == 200


async def test_email_verify_expired_token_rejected(client, session):
    user = await create_user(session, "expired@test.dev", "password123")
    await session.commit()
    now = datetime.now(UTC)
    stale = jose_jwt.encode(
        {"sub": str(user.id), "typ": "email_verify", "iat": now - timedelta(hours=25),
         "exp": now - timedelta(hours=1)},
        settings.secret_key, algorithm="HS256",
    )
    resp = await client.post(f"{PREFIX}/verify-email", json={"token": stale})
    assert resp.status_code == 401


async def test_resend_verification_rate_limited(client):
    """登录态重发:首次 200,分钟窗内第二次 429。"""
    await _register(client, "resend@test.dev")
    login = await _login(client, "resend@test.dev")
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    r1 = await client.post(f"{PREFIX}/resend-verification", headers=headers)
    assert r1.status_code == 200
    r2 = await client.post(f"{PREFIX}/resend-verification", headers=headers)
    assert r2.status_code == 429


async def test_verified_user_resend_is_noop(client, session):
    """已验证用户重发:200 且提示已验证(不再投递)。"""
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    user = await create_user(session, "verified@test.dev", "password123")
    from datetime import datetime as _dt

    user.email_verified_at = _dt.now(UTC)
    await session.commit()
    app.dependency_overrides.pop(get_current_user, None)  # 还原真实鉴权
    token = tk.create_access_token(str(user.id), user.role.value)
    resp = await client.post(
        f"{PREFIX}/resend-verification", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json().get("message") == "邮箱已验证"


# ── B2 OAuth state / 飞书 mock ────────────────────────────────


async def test_oauth_state_roundtrip():
    from fastapi import Request, Response

    import agentplatform.api.auth_ext as ax

    resp = Response()
    state = ax.new_oauth_state()
    ax.set_oauth_state_cookie(resp, state)
    cookie = resp.headers.get("set-cookie", "")
    assert "oauth_state=" in cookie and "HttpOnly" in cookie

    req = Request(scope={"type": "http", "headers": [(b"cookie", f"oauth_state={state}".encode())]})
    assert ax.check_oauth_state(req, state)
    assert not ax.check_oauth_state(req, "tampered-state")


async def test_callback_rejects_bad_state(client, monkeypatch):
    """state 不匹配 → 直接 error 回调,不触达上游。"""
    import agentplatform.api.auth_ext as ax

    async def _boom(*a, **k):  # 上游绝不应被调用
        raise AssertionError("state 校验失败时不应请求上游")

    monkeypatch.setattr(ax.httpx, "AsyncClient", _boom)
    settings.github_client_id = "x"
    settings.github_client_secret = "y"
    try:
        resp = await client.get(f"{PREFIX}/github/callback", params={"code": "c", "state": "bad"})
        assert resp.status_code == 307
        assert "error=oauth_state" in resp.headers["location"]
    finally:
        settings.github_client_id = ""
        settings.github_client_secret = ""


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


class _FakeFeishuClient:
    """飞书上游桩:v2 换 token(顶层字段)+ v1 user_info(data 包装)。"""

    user_info: ClassVar[dict] = {
        "union_id": "on_union_abc123",
        "open_id": "ou_open_abc123",
        "email": "feishu-user@corp.example",
        "name": "飞书用户",
    }

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        return _FakeResp({"code": 0, "access_token": "u-fake", "token_type": "Bearer"})

    async def get(self, url, headers=None):
        return _FakeResp({"code": 0, "data": dict(self.user_info)})


async def _feishu_flow(client, monkeypatch, fake_cls):
    import agentplatform.api.auth_ext as ax

    monkeypatch.setattr(ax.httpx, "AsyncClient", fake_cls)
    settings.feishu_app_id = "cli_fake"
    settings.feishu_app_secret = "sec_fake"
    try:
        start = await client.get(f"{PREFIX}/feishu", follow_redirects=False)
        assert start.status_code == 307
        assert "passport.feishu.cn" in start.headers["location"]
        state = client.cookies.get("oauth_state")
        assert state
        cb = await client.get(
            f"{PREFIX}/feishu/callback",
            params={"code": "c", "state": state},
            follow_redirects=False,
        )
        assert cb.status_code == 307
        return cb
    finally:
        settings.feishu_app_id = ""
        settings.feishu_app_secret = ""


async def test_feishu_login_full_flow(client, session, monkeypatch):
    """建号 + identity + 已验证 + 双令牌;token 参数可作 access。"""
    cb = await _feishu_flow(client, monkeypatch, _FakeFeishuClient)
    loc = cb.headers["location"]
    assert loc.startswith("/auth?token=") and "feishu=1" in loc
    assert "rf=" in cb.headers.get("set-cookie", "")

    ident = await session.scalar(select(UserIdentity).where(UserIdentity.provider == "feishu"))
    assert ident is not None and ident.provider_uid == "on_union_abc123"
    user = await session.get(User, ident.user_id)
    assert user.email == "feishu-user@corp.example"
    assert user.email_verified_at is not None

    token = loc.split("token=")[1].split("&")[0]
    me = await client.get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


async def test_feishu_no_email_placeholder(client, session, monkeypatch):
    """飞书邮箱不可见:合成占位邮箱,不标记已验证。"""

    class _NoEmail(_FakeFeishuClient):
        user_info: ClassVar[dict] = {"union_id": "on_union_xyz", "open_id": "ou_xyz"}

    cb = await _feishu_flow(client, monkeypatch, _NoEmail)
    assert "feishu=1" in cb.headers["location"]
    ident = await session.scalar(select(UserIdentity).where(UserIdentity.provider == "feishu"))
    user = await session.get(User, ident.user_id)
    assert user.email.endswith("@feishu.local")
    assert user.email_verified_at is None


# ── P3 登录设备管理(需求 013 C1)────────────────────────────


async def test_login_sessions_lists_and_kicks(client):
    """登录 → 设备列表含该族;下线后 refresh 失效、列表转历史。"""
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    await _register(client, "dev1@test.dev")
    login = await _login(client, "dev1@test.dev")
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    app.dependency_overrides.pop(get_current_user, None)  # /sessions 走真实鉴权

    listed = await client.get(f"{PREFIX}/sessions", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    mine = [r for r in rows if r["active"]]
    assert len(mine) >= 1
    fam = mine[0]["family_id"]
    assert mine[0]["ip"] != ""  # 设备指纹字段在

    kick = await client.delete(f"{PREFIX}/sessions/{fam}", headers=headers)
    assert kick.status_code == 200
    # 该族已吊销 → refresh 401
    again = await client.post(f"{PREFIX}/refresh")
    assert again.status_code == 401
    # 列表转为历史(不活跃)
    listed2 = await client.get(f"{PREFIX}/sessions", headers=headers)
    fams = {r["family_id"]: r["active"] for r in listed2.json()}
    assert fams.get(fam) is False


async def test_kick_unknown_family_404(client):
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    await _register(client, "dev2@test.dev")
    login = await _login(client, "dev2@test.dev")
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    app.dependency_overrides.pop(get_current_user, None)
    resp = await client.delete(f"{PREFIX}/sessions/00000000-0000-0000-0000-000000000000", headers=headers)
    assert resp.status_code == 404
