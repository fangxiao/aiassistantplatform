"""插件运行时环境管理与持久化目录约定。

约定与规范：
1. 插件专属持久化数据目录：~/.agentplatform/plugins/<plugin_name>/data/
2. 注入环境变量：
   - AGENTPLATFORM_PLUGIN_DATA_DIR: 插件专属持久化目录 (生命周期独立于代码包部署)
   - AGENTPLATFORM_BASE_URL: 平台服务基础地址 (默认 http://localhost:8000)
"""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path

import yaml


def get_plugin_data_dir(plugin_name: str | None = None) -> Path:
    """获取插件专属持久化数据目录。"""
    env_dir = os.environ.get("AGENTPLATFORM_PLUGIN_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
    else:
        name = plugin_name or "default"
        path = Path.home() / ".agentplatform" / "plugins" / name / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_plugin_env(
    root: Path | None = None,
    plugin_name: str | None = None,
    target_url: str | None = None,
) -> Path:
    """初始化插件执行环境与环境变量。

    1. 解析 plugin_name：若显式指定则用之；否则从 root / plugin.yaml 读取；若未找到则用 root.name。
    2. 准备数据目录 ~/.agentplatform/plugins/<name>/data/ 并创建；
    3. 注入环境变量 AGENTPLATFORM_PLUGIN_DATA_DIR；
    4. 注入环境变量 AGENTPLATFORM_BASE_URL。
    """
    resolved_name = plugin_name
    if not resolved_name and root is not None:
        manifest_path = root / "plugin.yaml"
        if manifest_path.exists():
            with suppress(Exception):
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("name"):
                    resolved_name = str(raw["name"])
        if not resolved_name:
            resolved_name = root.resolve().name

    data_dir = get_plugin_data_dir(resolved_name)
    os.environ["AGENTPLATFORM_PLUGIN_DATA_DIR"] = str(data_dir)

    base_url = (
        target_url
        or os.environ.get("AGENTPLATFORM_BASE_URL")
        or os.environ.get("AGENTPLATFORM_TARGET")
        or "http://localhost:8000"
    ).rstrip("/")
    os.environ.setdefault("AGENTPLATFORM_BASE_URL", base_url)

    return data_dir
