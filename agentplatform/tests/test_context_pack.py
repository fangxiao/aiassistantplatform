"""M27 组织上下文包测试(需求 016/设计 021)。

覆盖:建包(标记+四分区预置)、批量挂载(幂等/权限/404)、
运行时成员资格过滤(shared 包挂插件后:成员可检索、非成员检索不到)。
"""

import uuid

from sqlalchemy import select

from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.kb.model import KnowledgeBase, KbVisibility
from agentplatform.core.plugin.model import Plugin


async def _user(session, email: str, role: UserRole = UserRole.user) -> User:
    u = await create_user(session, email, "password123", role)
    await session.commit()
    return u


async def _plugin(session, owner: User, name: str) -> Plugin:
    p = Plugin(
        id=uuid.uuid4(), name=name, version="1.0.0", owner_id=str(owner.id),
        status="active", manifest={"display_name": name},
    )
    session.add(p)
    await session.commit()
    return p


# ── 建包 ──────────────────────────────────────────────────────


async def test_create_context_pack_presets_sections(client, session):
    from agentplatform.core.kb.model import KbDocument

    admin = await _user(session, "pack-admin@test.dev", UserRole.admin)
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    app.dependency_overrides[get_current_user] = lambda: admin
    resp = await client.post(
        "/api/kb/kbs",
        json={"name": "云舟科技", "slug": "yunzhou_pack", "context_pack": True},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_context_pack"] is True
    assert body["visibility"] == "shared"

    docs = (
        await session.scalars(
            select(KbDocument).where(KbDocument.kb_id == uuid.UUID(body["id"]))
        )
    ).all()
    names = {d.filename for d in docs}
    assert names == {"术语表.md", "业务规范.md", "决策记录.md", "常用联系人.md"}


async def test_create_normal_kb_unaffected(client, session):
    from agentplatform.core.kb.model import KbDocument

    u = await _user(session, "pack-normal@test.dev")
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.main import app

    app.dependency_overrides[get_current_user] = lambda: u
    resp = await client.post(
        "/api/kb/kbs", json={"name": "普通库", "slug": "normal_kb"}
    )
    assert resp.status_code == 201
    assert resp.json()["is_context_pack"] is False
    docs = (
        await session.scalars(
            select(KbDocument).where(KbDocument.kb_id == uuid.UUID(resp.json()["id"]))
        )
    ).all()
    assert docs == []  # 无预置


# ── 批量挂载 ──────────────────────────────────────────────────


async def _make_pack(session, owner: User) -> KnowledgeBase:
    from agentplatform.core.kb.service import create_kb

    return await create_kb(
        session, name="组织包", slug=f"pack_{uuid.uuid4().hex[:8]}",
        owner=owner, context_pack=True,
    )


async def test_mount_batch_idempotent_and_permission(client, session):
    from agentplatform.core.auth.dependencies import get_current_user
    from agentplatform.core.kb.service import add_member
    from agentplatform.main import app

    owner = await _user(session, "pack-owner@test.dev")
    member = await _user(session, "pack-member@test.dev")
    outsider = await _user(session, "pack-outsider@test.dev")
    pack = await _make_pack(session, owner)
    await add_member(session, pack, owner, member=member)
    await session.commit()

    p1 = await _plugin(session, owner, "助手A")
    p2 = await _plugin(session, owner, "助手B")

    # 非管理员(outsider)挂载 → 403
    app.dependency_overrides[get_current_user] = lambda: outsider
    resp = await client.post(
        f"/api/kb/kbs/{pack.id}/mount-batch", json={"plugin_ids": [str(p1.id)]}
    )
    assert resp.status_code == 403

    # owner 批量挂载 → 两个助手各写入,幂等(重复挂不重复)
    app.dependency_overrides[get_current_user] = lambda: owner
    resp = await client.post(
        f"/api/kb/kbs/{pack.id}/mount-batch",
        json={"plugin_ids": [str(p1.id), str(p2.id)]},
    )
    assert resp.status_code == 200 and resp.json()["mounted"] == 2
    await client.post(
        f"/api/kb/kbs/{pack.id}/mount-batch", json={"plugin_ids": [str(p1.id)]}
    )
    await session.refresh(p1)
    assert p1.mounted_kb_ids == [str(pack.id)]

    # 挂到他人插件 → 404
    other_plugin = await _plugin(session, member, "成员自己的助手")
    resp = await client.post(
        f"/api/kb/kbs/{pack.id}/mount-batch", json={"plugin_ids": [str(other_plugin.id)]}
    )
    assert resp.status_code == 404


# ── 运行时成员资格过滤 ────────────────────────────────────────


async def test_runtime_filter_member_vs_outsider(session):
    """shared 包经插件挂载:成员 resolve 出、非成员被过滤(设计 021 §3)。"""
    from agentplatform.core.kb.search_tool import resolve_allowed_kb_ids
    from agentplatform.core.kb.service import add_member

    owner = await _user(session, "rt-owner@test.dev")
    member = await _user(session, "rt-member@test.dev")
    outsider = await _user(session, "rt-out@test.dev")
    pack = await _make_pack(session, owner)
    await add_member(session, pack, owner, member=member)
    await session.commit()

    allowed_member = await resolve_allowed_kb_ids(
        session, mounted_kb_ids=[], plugin_manifest=None,
        plugin_mounted_kb_ids=[pack.id], session_user_id=str(member.id),
    )
    allowed_owner = await resolve_allowed_kb_ids(
        session, mounted_kb_ids=[], plugin_manifest=None,
        plugin_mounted_kb_ids=[pack.id], session_user_id=str(owner.id),
    )
    allowed_outsider = await resolve_allowed_kb_ids(
        session, mounted_kb_ids=[], plugin_manifest=None,
        plugin_mounted_kb_ids=[pack.id], session_user_id=str(outsider.id),
    )
    allowed_anon = await resolve_allowed_kb_ids(
        session, mounted_kb_ids=[], plugin_manifest=None,
        plugin_mounted_kb_ids=[pack.id],
    )
    assert pack.id in allowed_member
    assert pack.id in allowed_owner  # owner 天然成员
    assert pack.id not in allowed_outsider
    assert pack.id not in allowed_anon  # 无用户上下文不放进 shared
    assert pack.visibility == KbVisibility.shared
