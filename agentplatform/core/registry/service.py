"""skill/tool 注册表服务(设计 002 §3.1 / 004 §skill_tools)。

职责:公共资源查询、按 id 取版本、版本约束解析(^ / ~)、
插件部署时的 depends_on 校验;内置资源种子与插件部署共用 register()。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.model import (
    SkillTool,
    SkillToolKind,
    SkillToolSource,
)
from agentplatform.core.registry.version import parse, resolve_highest

PUBLIC_SOURCES = (SkillToolSource.builtin, SkillToolSource.shared)


async def list_public(
    session: AsyncSession, kind: SkillToolKind | None = None
) -> list[SkillTool]:
    """公共资源(builtin + shared);kind 可选过滤;按 name 升序。"""
    stmt = select(SkillTool).where(SkillTool.source.in_(PUBLIC_SOURCES))
    if kind is not None:
        stmt = stmt.where(SkillTool.kind == kind)
    rows = await session.scalars(stmt.order_by(SkillTool.name, SkillTool.version))
    return list(rows)


def latest_of_each(rows: list[SkillTool]) -> list[SkillTool]:
    """每个 id 只保留最高版本(列表接口用,避免一个资源占多行)。"""
    best: dict[str, SkillTool] = {}
    for r in rows:
        cur = best.get(r.id)
        if cur is None or parse(r.version) > parse(cur.version):
            best[r.id] = r
    return list(best.values())


async def get_versions(session: AsyncSession, resource_id: str) -> list[SkillTool]:
    """按 id 取全部版本,按 semver 升序(注册表规模小,内存排序更可靠)。"""
    rows = await session.scalars(select(SkillTool).where(SkillTool.id == resource_id))
    return sorted(rows, key=lambda r: parse(r.version))


async def resolve(
    session: AsyncSession, resource_id: str, constraint: str | None = None
) -> SkillTool | None:
    """解析资源:无约束取最高版本;有约束取满足 ^ / ~ 的最高版本,无匹配返回 None。"""
    rows = await get_versions(session, resource_id)
    if not rows:
        return None
    best = resolve_highest([r.version for r in rows], constraint)
    if best is None:
        return None
    return next(r for r in rows if r.version == best)


def split_dependency(dep: str) -> tuple[str, str | None]:
    """'tool:pdf_parse@^1.0' -> ('tool:pdf_parse', '^1.0')。"""
    if "@" in dep:
        resource_id, _, constraint = dep.partition("@")
        return resource_id, constraint
    return dep, None


async def check_dependencies(session: AsyncSession, deps: list[str]) -> list[str]:
    """校验插件 depends_on:返回未满足的依赖(空列表 = 全部满足)。"""
    missing: list[str] = []
    for dep in deps:
        resource_id, constraint = split_dependency(dep)
        if await resolve(session, resource_id, constraint) is None:
            missing.append(dep)
    return missing


async def seed_builtin(session: AsyncSession) -> int:
    """登记全部内置资源(幂等:同 id+version 覆盖更新)。返回登记条数。"""
    from agentplatform.core.registry.builtin import ALL

    count = 0
    for res in ALL:
        await register(
            session,
            resource_id=res["id"],
            kind=SkillToolKind(res["kind"]),
            name=res["name"],
            version=res["version"],
            source=SkillToolSource.builtin,
            schema_=res["schema"],
            impl_path=f"agentplatform.core.registry.builtin.{res['name'].replace('-', '_')}",
            description=res["description"],
        )
        count += 1
    await session.commit()
    return count


async def register(
    session: AsyncSession,
    *,
    resource_id: str,
    kind: SkillToolKind,
    name: str,
    version: str,
    source: SkillToolSource,
    schema_: dict,
    impl_path: str | None = None,
    description: str | None = None,
    owner_id: str | None = None,
) -> SkillTool:
    """注册资源;同 (id, version) 已存在则更新,否则新增(种子/插件部署共用)。"""
    existing = await session.get(SkillTool, (resource_id, version))
    if existing is not None:
        existing.kind = kind
        existing.name = name
        existing.source = source
        existing.schema_ = schema_
        existing.impl_path = impl_path
        existing.description = description
        existing.owner_id = owner_id
        await session.flush()
        return existing
    row = SkillTool(
        id=resource_id,
        version=version,
        kind=kind,
        name=name,
        source=source,
        schema_=schema_,
        impl_path=impl_path,
        description=description,
        owner_id=owner_id,
    )
    session.add(row)
    await session.flush()
    return row
