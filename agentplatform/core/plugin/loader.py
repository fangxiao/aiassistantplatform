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
from agentplatform.core.plugin.model import Plugin, PluginReviewStatus, PluginStatus
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

    # 试用期免审(20260930 用户决策):部署即 approved;对外开放前
    # settings.plugin_review_required=True 恢复 ADR 0008 审批制
    from agentplatform.config import settings as _settings

    trial_status = (
        PluginReviewStatus.pending_review
        if _settings.plugin_review_required
        else PluginReviewStatus.approved
    )
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
        # ADR 0008 保守策略:重新部署一律退回待审,防"过审后偷换内容"(审批制下)
        existing.review_status = trial_status
        existing.last_review_reason = None
        if _settings.plugin_review_required:
            existing.reviewed_by = None
            existing.reviewed_at = None
        plugin = existing
        await session.flush()
    else:
        plugin = Plugin(
            name=manifest.name,
            version=manifest.version,
            manifest=manifest.model_dump(),
            status=PluginStatus.active,
            owner_id=owner_id,
            review_status=trial_status,
        )
        session.add(plugin)
        await session.flush()

    # T18.3 插件级必经步骤:并入每个自有资源(任一执行即触发终答校验)
    plugin_level_rt = [str(x) for x in (getattr(manifest, "required_tools", None) or [])]
    if plugin_level_rt:
        for r in [*manifest.skills, *manifest.tools]:
            merged = dict(r.schema_ or {})
            own = [str(x) for x in (merged.get("required_tools") or [])]
            merged["required_tools"] = list(dict.fromkeys(own + plugin_level_rt))
            r.schema_ = merged
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
    # T18.3:交付必经步骤声明随 schema_ 持久化(loop 终答前校验用,免独立列)
    if getattr(res, "required_tools", None):
        merged_schema = dict(res.schema_ or {})
        merged_schema["required_tools"] = list(res.required_tools)
        res.schema_ = merged_schema
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


def is_plugin_owner(plugin: Plugin, user) -> bool:
    """当前用户是否该插件 owner(admin 豁免,015 §4.2)。"""
    from agentplatform.core.auth.dependencies import is_admin

    return user is not None and (
        is_admin(user) or plugin.owner_id == str(user.id)
    )


def is_plugin_visible(plugin: Plugin, user) -> bool:
    """全员可见性判定(015 §5,收敛点):active+approved,owner/admin 全量可见。

    未来付费分层(access_tier)只在此处扩展。
    """
    from agentplatform.core.auth.dependencies import is_admin

    if user is not None and (is_admin(user) or plugin.owner_id == str(user.id)):
        return True
    return (
        plugin.status == PluginStatus.active
        and plugin.review_status == PluginReviewStatus.approved
    )


async def set_review(
    session: AsyncSession,
    plugin: Plugin,
    status: PluginReviewStatus,
    reviewer_id: str,
    reason: str | None = None,
) -> Plugin:
    """审批动作留痕(015 §5);重提/过审清空驳回原因。"""
    plugin.review_status = status
    plugin.reviewed_by = reviewer_id
    plugin.reviewed_at = datetime.now(UTC)
    plugin.last_review_reason = reason if status == PluginReviewStatus.rejected else None
    await session.flush()
    return plugin


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


async def ensure_resource_impl(session: AsyncSession, resource: SkillTool) -> None:
    """部署态自愈:私有资源 impl 文件缺失时,从插件 manifest 内联代码落盘重建。

    背景(20260929 sharestudy 事故):历史部署残留的旧版本资源行 impl_path 指向
    开发者宿主机路径,服务端容器内不存在;execute_skill 曾静默降级为按 description
    拼提示词,LLM 拿到"说明书本身",表现为"skill 未执行、模型裸手发挥"。
    在会话资源装载点检测并自愈,使陈旧资源行自动修复;无法自愈时记日志留痕。
    """
    import logging as _logging

    if resource.source != SkillToolSource.private or not resource.impl_path:
        return
    if Path(resource.impl_path).exists():
        return

    plugin_name = resource.owner_id or resource.id.split(":", 1)[-1].rsplit("_", 1)[0]
    plugin = await session.scalar(select(Plugin).where(Plugin.name == plugin_name))
    code, file_name = None, Path(resource.impl_path).name
    if plugin is not None:
        for entry in (plugin.manifest.get("skills") or []) + (
            plugin.manifest.get("tools") or []
        ):
            if isinstance(entry, dict) and entry.get("id") == resource.id and entry.get("code"):
                code = entry["code"]
                file_name = Path(entry.get("file") or file_name).name or file_name
                break
    if code is None:
        _logging.getLogger(__name__).warning(
            "资源 %s@%s impl 文件缺失且无法从 manifest 自愈: %s",
            resource.id,
            resource.version,
            resource.impl_path,
        )
        return

    target = (
        Path.home()
        / ".agentplatform"
        / "installed_plugins"
        / plugin_name
        / ("skills" if resource.kind == SkillToolKind.skill else "tools")
        / file_name
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    resource.impl_path = str(target.resolve())
    await session.flush()
    _logging.getLogger(__name__).warning(
        "资源 %s@%s impl 文件缺失,已从 manifest 自愈落盘: %s",
        resource.id,
        resource.version,
        resource.impl_path,
    )


async def uninstall_plugin(session: AsyncSession, plugin: Plugin) -> None:
    """删除插件及其私有 skill/tool(注册表 source=private)。"""
    await purge_private_resources(session, plugin.name)
    remove_plugin_storage(plugin.name)
    await session.delete(plugin)
    await session.flush()

