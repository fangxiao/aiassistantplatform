"""插件加载器(设计 006 / 004 §plugins / 002 §4 / ADR 0007)。

部署流程:清单校验 -> depends_on 依赖解析(注册表,复用 M2)
-> 按 name 登记/覆盖插件 -> 登记插件自有 skill/tool(注册表 source=private)。
skill/tool 代码加载与执行在 M5 引入;卸载时清理插件及其私有资源。

ADR 0007:插件名全局唯一,同名重部署原地覆盖(保留行 UUID 与历史会话,
清掉旧版本私有资源),不保留历史版本。
"""

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.plugin.errors import DependencyError, PluginValidationError
from agentplatform.core.plugin.manifest import PluginManifest, ResourceDef, validate_manifest
from agentplatform.core.plugin.model import Plugin, PluginStatus
from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import check_dependencies, register


async def deploy_plugin(
    session: AsyncSession,
    manifest: PluginManifest,
    owner_id: str | None = None,
) -> Plugin:
    """部署插件:校验 + 依赖解析 + 按 name 登记或原地覆盖(ADR 0007)。

    同名插件重部署时保留行 UUID(历史会话不悬挂)与首次部署者 owner_id,
    替换清单/版本标签/部署时间,旧版本私有注册表资源在资源重登记前清除。
    """
    validate_manifest(manifest)

    missing = await check_dependencies(session, manifest.depends_on)
    if missing:
        raise DependencyError(missing)

    existing = await session.scalar(
        select(Plugin).where(Plugin.name == manifest.name)
    )
    if existing is not None:
        # 原地覆盖:先删该插件名下全部私有资源(含旧版本),随后按新清单重登记
        await purge_private_resources(session, manifest.name)
        remove_plugin_storage(manifest.name)
        existing.version = manifest.version
        existing.manifest = manifest.model_dump()
        existing.status = PluginStatus.active
        existing.deployed_at = datetime.now(UTC)
        plugin = existing
        await session.flush()
    else:
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

    from agentplatform.core.plugin.env import get_plugin_data_dir

    get_plugin_data_dir(manifest.name)
    return plugin


async def _register_resource(
    session: AsyncSession,
    res: ResourceDef,
    kind: SkillToolKind,
    manifest: PluginManifest,
) -> None:
    impl_path = res.file
    if res.code:
        storage_dir = (
            Path.home()
            / ".agentplatform"
            / "installed_plugins"
            / manifest.name
            / ("skills" if kind == SkillToolKind.skill else "tools")
        )
        storage_dir.mkdir(parents=True, exist_ok=True)
        file_name = Path(res.file).name or f"{res.id.split(':', 1)[1]}.py"
        target_file = storage_dir / file_name
        target_file.write_text(res.code, encoding="utf-8")
        impl_path = str(target_file.resolve())

    # T11.10:本地回退实现允许与可选依赖同 id(不同版本共存,运行时公共优先解析),
    # 但同 (id, version) 撞键会经 register() 覆盖平台公共资源,必须提前拒绝。
    existing_pk = await session.get(SkillTool, (res.id, manifest.version))
    if existing_pk is not None and existing_pk.source in (
        SkillToolSource.builtin,
        SkillToolSource.shared,
    ):
        raise PluginValidationError(
            f"自有资源 {res.id}@{manifest.version} 与平台公共资源撞 id+version,"
            "回退实现请使用插件自身版本号"
        )

    await register(
        session,
        resource_id=res.id,
        kind=kind,
        name=res.id.split(":", 1)[1],
        version=manifest.version,
        source=SkillToolSource.private,
        schema_=res.schema_ or {"parameters": {"type": "object"}},
        impl_path=impl_path,
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


async def purge_private_resources(session: AsyncSession, plugin_name: str) -> None:
    """删除插件名下全部私有注册表资源(所有版本;owner_id 即插件名)。"""
    await session.execute(
        sa.delete(SkillTool).where(
            SkillTool.owner_id == plugin_name,
            SkillTool.source == SkillToolSource.private,
        )
    )


def remove_plugin_storage(plugin_name: str) -> None:
    """删除插件代码存储目录(~/.agentplatform/installed_plugins/<name>)。"""
    plugin_storage = Path.home() / ".agentplatform" / "installed_plugins" / plugin_name
    if plugin_storage.exists():
        shutil.rmtree(plugin_storage, ignore_errors=True)


async def uninstall_plugin(session: AsyncSession, plugin: Plugin) -> None:
    """删除插件及其私有 skill/tool(注册表 source=private)。"""
    await purge_private_resources(session, plugin.name)
    remove_plugin_storage(plugin.name)
    await session.delete(plugin)
    await session.flush()

