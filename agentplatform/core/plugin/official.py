"""官方插件启动部署器(M35/20261012 双层生态)。

启动时扫描 plugins/ 目录下的 plugin.yaml,author 含 AgentPlatform/Official/官方
的插件自动部署/升级(幂等,同名原地覆盖);非官方目录内容不动。
"""

import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_OFFICIAL_KEYWORDS = ("AgentPlatform", "Official", "官方")


def _is_official_manifest(manifest) -> bool:
    """兼容 dict 与 PluginManifest(Pydantic 用属性访问非 .get)。"""
    author = getattr(manifest, "author", None) or (manifest.get("author") if isinstance(manifest, dict) else "") or ""
    return any(kw in author for kw in _OFFICIAL_KEYWORDS)


async def deploy_official_plugins(session: AsyncSession) -> int:
    """扫描 plugins/ 并部署官方插件;返回部署数(幂等,可重复调用)。"""
    from agentplatform.cli.yaml_io import load_manifest as _load_yaml
    from agentplatform.core.plugin.loader import deploy_plugin
    from agentplatform.core.plugin.manifest import PluginManifest

    plugins_dir = Path(__file__).parent.parent.parent / "plugins"
    if not plugins_dir.is_dir():
        return 0

    deployed = 0
    for plugin_dir in sorted(plugins_dir.iterdir()):
        yaml_path = plugin_dir / "plugin.yaml"
        if not yaml_path.is_file():
            continue
        try:
            manifest = PluginManifest(**_load_yaml(yaml_path))
            if not _is_official_manifest(manifest):
                continue
            await deploy_plugin(session, manifest, owner_id=None)
            deployed += 1
            logger.info("官方插件已部署: %s v%s", manifest.name, manifest.version)
        except Exception as exc:  # noqa: BLE001 单插件失败不影响其他
            logger.warning("官方插件部署失败 %s: %s", plugin_dir.name, exc)
    return deployed
