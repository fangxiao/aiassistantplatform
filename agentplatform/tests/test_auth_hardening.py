"""认证加固专项测试(M24/需求 013):邀请码/PAT/限频。

直接驱动核心函数(DB + get_current_user),不经 HTTP 夹具层;
HTTP 侧接线(auth.py 限频/邀请分支)由全量回归的旁路夹具覆盖。
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.oauth_model import InviteCode, PersonalAccessToken


# ── 邀请码 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consume_invite_valid_exhausted_invalid(session: AsyncSession) -> None:
    from agentplatform.api.auth_ext import consume_invite
    from agentplatform.core.auth.errors import AuthError

    session.add(
        InviteCode(code="inv-good01", max_uses=1, expires_at=datetime.now(UTC) + timedelta(days=1))
    )
    session.add(InviteCode(code="inv-expired", max_uses=1, expires_at=datetime.now(UTC) - timedelta(days=1)))
    session.add(InviteCode(code="inv-off", max_uses=1, disabled=True))
    session.add(InviteCode(code="inv-multi", max_uses=2, used_count=1))
    await session.commit()

    await consume_invite(session, "inv-good01")  # 有效:核销不抛
    for bad in ("inv-none", "inv-expired", "inv-off"):
        with pytest.raises(AuthError):
            await consume_invite(session, bad)
    # inv-multi 剩 1 次:可用,再核销即用尽
    await consume_invite(session, "inv-multi")
    with pytest.raises(AuthError):
        await consume_invite(session, "inv-multi")


# ── PAT ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pat_authenticate_and_revoke(session: AsyncSession) -> None:
    """PAT 经 get_current_user 真实路径认证;撤销后失效。"""
    import hashlib
    import secrets

    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.core.auth.model import UserRole
    from agentplatform.core.auth.service import create_user

    user = await create_user(session, "pat-owner@test.dev", "password123", UserRole.user)
    raw = f"ap_{secrets.token_urlsafe(30)}"
    pat = PersonalAccessToken(
        user_id=user.id, name="ci", token_hash=hashlib.sha256(raw.encode()).hexdigest(), prefix=raw[:8]
    )
    session.add(pat)
    await session.commit()

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw)
    me = await get_current_user(creds, session)
    assert str(me.id) == str(user.id)
    assert pat.last_used_at is not None

    pat.revoked_at = datetime.now(UTC)
    await session.commit()
    with pytest.raises(Exception) as exc_info:
        await get_current_user(creds, session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_pat_garbage_rejected(session: AsyncSession) -> None:
    from agentplatform.core.auth.dependencies import get_current_user

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="ap_not_a_real_token_xxxxxxxx")
    with pytest.raises(Exception) as exc_info:
        await get_current_user(creds, session)
    assert exc_info.value.status_code == 401


# ── 限频 ────────────────────────────────────────────────


def test_rate_limit_and_lockout_real_functions() -> None:
    """真实限频函数:IP 滑窗与账号锁定语义(A5)。"""
    import importlib

    import agentplatform.core.auth.ratelimit as _mod

    rl = importlib.reload(_mod)  # conftest 已 stub 模块属性,reload 取回真实函数

    for _ in range(5):
        assert rl.allow_ip_auth("9.9.9.9")
    assert not rl.allow_ip_auth("9.9.9.9")  # 第 6 次拒绝
    assert rl.allow_ip_auth("8.8.8.8")  # 其他 IP 不受影响

    for _ in range(3):
        assert rl.allow_ip_register("9.9.9.9")
    assert not rl.allow_ip_register("9.9.9.9")  # 注册 3/小时

    for _ in range(5):
        rl.record_login_fail("victim@test.dev")
    assert rl.account_locked("victim@test.dev")
    rl.clear_login_fail("victim@test.dev")
    assert not rl.account_locked("victim@test.dev")
