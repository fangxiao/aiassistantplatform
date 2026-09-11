"""skill/tool 注册表服务(设计 002 §3.1 / 004 §skill_tools)。

职责:公共资源查询、按 id 取版本、版本约束解析(^ / ~)、
插件部署时的 depends_on 校验;内置资源种子与插件部署共用 register()。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.model import (
    SkillTool,
    SkillToolKind,
    SkillToolSource,
)
from agentplatform.core.registry.version import parse, resolve_highest

PUBLIC_SOURCES = (SkillToolSource.builtin, SkillToolSource.shared)


@dataclass(frozen=True)
class ParsedDependency:
    """depends_on 单项解析结果(T11.10)。

    optional=True 对应 'tool:html_cleaner@^1.0?' 语法:平台有满足版本则用
    平台版,缺失时回退插件本地同名实现,部署不因平台缺失而阻断。
    """

    resource_id: str
    constraint: str | None
    optional: bool


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
    """运行时解析资源:公共资源(builtin/shared)优先,其次插件私有实现。

    无约束取最高版本;有约束取满足 ^ / ~ 的最高版本,无匹配返回 None。
    公共优先是 T11.10 可选依赖回退的基础:同名时平台版胜出,平台缺失才用
    插件本地实现;同时避免插件私有高版本号"顶掉"平台内置资源。
    """
    rows = await get_versions(session, resource_id)
    if not rows:
        return None
    public = [r for r in rows if r.source in PUBLIC_SOURCES]
    for candidates in (public, rows):
        best = resolve_highest([r.version for r in candidates], constraint)
        if best is not None:
            return next(r for r in candidates if r.version == best)
    return None


async def resolve_public(
    session: AsyncSession, resource_id: str, constraint: str | None = None
) -> SkillTool | None:
    """只在公共资源(builtin/shared)中解析;部署依赖校验用,私有资源不算满足。"""
    rows = [
        r
        for r in await get_versions(session, resource_id)
        if r.source in PUBLIC_SOURCES
    ]
    best = resolve_highest([r.version for r in rows], constraint)
    if best is None:
        return None
    return next(r for r in rows if r.version == best)


def split_dependency(dep: str) -> tuple[str, str | None]:
    """'tool:pdf_parse@^1.0' -> ('tool:pdf_parse', '^1.0');兼容可选后缀 '?'。"""
    if dep.endswith("?"):
        dep = dep[:-1]
    if "@" in dep:
        resource_id, _, constraint = dep.partition("@")
        return resource_id, constraint
    return dep, None


def parse_dependency(dep: str) -> ParsedDependency:
    """解析 depends_on 单项,识别可选依赖后缀 '?'(T11.10)。"""
    optional = dep.endswith("?")
    resource_id, constraint = split_dependency(dep)
    return ParsedDependency(resource_id, constraint, optional)


async def check_dependencies(session: AsyncSession, deps: list[str]) -> list[str]:
    """校验插件 depends_on:返回未满足的必选依赖(空列表 = 校验通过)。

    - 必选依赖:平台公共资源必须存在且满足版本约束;其他插件的私有资源不算满足。
    - 可选依赖(以 '?' 结尾,如 tool:html_cleaner@^1.0?):平台缺失时回退插件
      本地同名实现,不阻断部署(T11.10)。
    """
    missing: list[str] = []
    for dep in deps:
        parsed = parse_dependency(dep)
        if parsed.optional:
            continue
        if await resolve_public(session, parsed.resource_id, parsed.constraint) is None:
            missing.append(dep)
    return missing


async def seed_builtin(session: AsyncSession) -> int:
    """登记全部内置资源(幂等:同 id+version 覆盖更新)。返回登记条数。"""
    from agentplatform.core.registry.builtin import ALL

    count = 0
    for res in ALL:
        impl = res.get("impl_path") or f"agentplatform.core.registry.builtin.{res['name'].replace('-', '_')}"
        await register(
            session,
            resource_id=res["id"],
            kind=SkillToolKind(res["kind"]),
            name=res["name"],
            version=res["version"],
            source=SkillToolSource.builtin,
            schema_=res["schema"],
            impl_path=impl,
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
