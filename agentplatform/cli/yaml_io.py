"""plugin.yaml 读写(006 §2;PyYAML)。"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]


def load_manifest(path: Path) -> dict:
    """读取并解析 plugin.yaml;返回 dict。"""
    if not path.exists():
        raise FileNotFoundError(f"未找到清单: {path}(先运行 init)")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise TypeError(f"{path} 不是合法的映射结构")
    return data


def dump_manifest(data: dict, path: Path) -> None:
    """写出 plugin.yaml(保持可读顺序)。"""
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
