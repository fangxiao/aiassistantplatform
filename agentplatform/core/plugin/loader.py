"""插件加载器(设计 006 / 004 §plugins / 002 §4)。

部署流程:清单校验 -> depends_on 依赖解析(注册表,复用 M2)
-> 登记插件 -> 登记插件自有 skill/tool(注册表 source=private)。
skill/tool 代码加载与执行在 M5 引入;卸载时清理插件及其私有资源。
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.plugin.errors import DependencyError, PluginValidationError
from agentplatform.core.plugin.manifest import PluginManifest, ResourceDef
from agentplatform.core.plugin.model import Plugin, PluginStatus
from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import check_dependencies, register
from agentplatform.core.registry.version import parse


def validate_manifest(manifest: PluginManifest) -> None:
    """结构校验;不通过抛 PluginValidationError。"""
    if not manifest.name.strip():
        raise PluginValidationError("name 不能为空")
    try:
        parse(manifest.version)
    except ValueError as exc:
        raise PluginValidationError(f"version 非法: {exc}") from exc
    for r in manifest.skills:
        if not r.id.startswith("skill:"):
            raise PluginValidationError(f"skill id 必须以 'skill:' 开头: {r.id}")
    for r in manifest.tools:
        if not r.id.startswith("tool:"):
            raise PluginValidationError(f"tool id 必须以 'tool:' 开头: {r.id}")


async def deploy_plugin(
    session: AsyncSession, manifest: PluginManifest, owner_id: str | None = None
) -> Plugin:
    """部署插件:校验 + 依赖解析 + 登记插件及其自有资源。"""
    validate_manifest(manifest)

    missing = await check_dependencies(session, manifest.depends_on)
    if missing:
        raise DependencyError(missing)

    existing = await session.scalar(
        select(Plugin).where(
            Plugin.name == manifest.name, Plugin.version == manifest.version
        )
    )
    if existing is not None:
        raise PluginValidationError(
            f"插件已存在: {manifest.name}@{manifest.version}(先卸载再重部署)"
        )

    plugin = Plugin(
        name=manifest.name,
        version=manifest.version,
        manifest=manifest.model_dump(),
        status=PluginStatus.active,
        owner_id=owner_id,
    )
    session.add(plugin)
    await session.flush()

    for r in manifest.skills:
        await _register_resource(session, r, SkillToolKind.skill, manifest)
    for r in manifest.tools:
        await _register_resource(session, r, SkillToolKind.tool, manifest)
    return plugin


async def _register_resource(
    session: AsyncSession,
    res: ResourceDef,
    kind: SkillToolKind,
    manifest: PluginManifest,
) -> None:
    await register(
        session,
        resource_id=res.id,
        kind=kind,
        name=res.id.split(":", 1)[1],
        version=manifest.version,
        source=SkillToolSource.private,
        schema_=res.schema_ or {"parameters": {"type": "object"}},
        impl_path=res.file,
        description=res.description,
        owner_id=manifest.name,  # 资源归属插件,便于卸载时按 owner 清理
    )


async def list_plugins(session: AsyncSession) -> list[Plugin]:
    rows = await session.scalars(select(Plugin).order_by(Plugin.deployed_at.desc()))
    return list(rows)


async def get_plugin(session: AsyncSession, plugin_id: uuid.UUID) -> Plugin | None:
    return await session.get(Plugin, plugin_id)


async def set_status(
    session: AsyncSession, plugin_id: uuid.UUID, status: PluginStatus
) -> Plugin | None:
    plugin = await get_plugin(session, plugin_id)
    if plugin is None:
        return None
    plugin.status = status
    await session.flush()
    return plugin


async def uninstall_plugin(session: AsyncSession, plugin: Plugin) -> None:
    """删除插件及其私有 skill/tool(注册表 source=private)。"""
    await session.execute(
        sa.delete(SkillTool).where(
            SkillTool.owner_id == plugin.name,
            SkillTool.version == plugin.version,
            SkillTool.source == SkillToolSource.private,
        )
    )
    await session.delete(plugin)
    await session.flush()
