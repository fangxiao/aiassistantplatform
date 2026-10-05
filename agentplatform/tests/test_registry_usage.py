"""M26 注册表热度测试(需求 015/设计 020)。

覆盖:计数自增埋点、manifest 计数注入与离线回退、registry API use_count/sort=usage。
"""

from sqlalchemy import select

from agentplatform.core.registry.capabilities import (
    get_capabilities_manifest,
    usage_by_id,
)
from agentplatform.core.registry.model import SkillTool


async def _seed(session, rid: str, kind: str, use_count: int) -> None:
    from agentplatform.core.registry.model import SkillToolKind

    row = SkillTool(
        id=rid,
        version="1.0.0",
        kind=SkillToolKind(kind),
        name=rid.split(":", 1)[1],
        source="builtin",
        schema_={"parameters": {"type": "object", "properties": {}}},
        use_count=use_count,
    )
    session.add(row)
    await session.flush()


# ── manifest 注入 ─────────────────────────────────────────────


async def test_manifest_injects_usage_and_falls_back(session):
    await _seed(session, "tool:hot_one", "tool", 42)
    await session.commit()

    usage = await usage_by_id(session)
    assert usage["tool:hot_one"] == 42

    m = get_capabilities_manifest(usage)
    # 注入只覆盖静态清单条目;清单内条目全部带 use_count 字段
    assert all("use_count" in t for t in m["builtin_tools"])
    assert all("use_count" in s for s in m["builtin_skills"])

    # 离线回退:不传 usage 全 0
    offline = get_capabilities_manifest()
    assert all(t["use_count"] == 0 for t in offline["builtin_tools"])


async def test_usage_by_id_sums_across_versions(session):
    from agentplatform.core.registry.model import SkillToolKind

    for ver, cnt in (("1.0.0", 3), ("1.1.0", 4)):
        session.add(
            SkillTool(
                id="tool:multi", version=ver, kind=SkillToolKind.tool, name="multi",
                source="builtin", schema_={}, use_count=cnt,
            )
        )
    await session.commit()
    assert (await usage_by_id(session))["tool:multi"] == 7


# ── 计数埋点 ──────────────────────────────────────────────────


async def test_bump_use_count_increments(session):
    """埋点助手:两次自增 → 2;不存在的资源行静默无操作(自愈语义)。"""
    from agentplatform.core.registry.service import bump_use_count

    await _seed(session, "tool:bump_me", "tool", 0)
    await session.commit()

    await bump_use_count(session, "tool:bump_me", "1.0.0")
    await bump_use_count(session, "tool:bump_me", "1.0.0")
    await session.commit()
    row = await session.scalar(select(SkillTool).where(SkillTool.id == "tool:bump_me"))
    assert row.use_count == 2

    # 不存在的资源/版本:静默不抛
    await bump_use_count(session, "tool:nope", "9.9.9")
    await bump_use_count(session, "tool:bump_me", "2.0.0")  # 版本不匹配
    await session.commit()
    row = await session.scalar(select(SkillTool).where(SkillTool.id == "tool:bump_me"))
    assert row.use_count == 2  # 未变化


# ── registry API ─────────────────────────────────────────────


async def test_registry_api_sort_usage(client, session):
    await _seed(session, "tool:z_low", "tool", 1)
    await _seed(session, "tool:a_high", "tool", 99)
    await session.commit()

    resp = await client.get("/api/registry/tools?sort=usage")
    assert resp.status_code == 200
    rows = resp.json()
    ids = [r["id"] for r in rows]
    assert ids.index("tool:a_high") < ids.index("tool:z_low")
    assert all("use_count" in r for r in rows)

    # 不传参:兼容既有顺序(不报错)
    resp2 = await client.get("/api/registry/tools")
    assert resp2.status_code == 200


async def test_capabilities_endpoint_carries_usage(client, session):
    await _seed(session, "tool:cap_probe", "tool", 5)
    await session.commit()
    resp = await client.get("/api/specs/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert all("use_count" in t for t in body["builtin_tools"])
