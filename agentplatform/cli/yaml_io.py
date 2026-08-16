"""plugin.yaml 读写 (支持 PyYAML 与内置安全降级解析器)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]

    HAS_PYYAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    HAS_PYYAML = False


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """极简无第三方依赖的 YAML 降级解析器 (用于在零依赖极简环境中解析 plugin.yaml)。"""
    lines = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    result: dict[str, Any] = {}
    current_list: list[Any] | None = None

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("- "):
            val = stripped[2:].strip().strip("\"'")
            if current_list is not None:
                # 检查是否是对象项 (如 - id: ...)
                if ":" in val and not val.startswith("tool:") and not val.startswith("skill:"):
                    k, _, v = val.partition(":")
                    current_list.append({k.strip(): v.strip().strip("\"'")})
                else:
                    current_list.append(val)
            continue

        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()

            if not v:
                # 列表开始
                current_list = []
                result[k] = current_list
            else:
                current_list = None
                if v.startswith("[") and v.endswith("]"):
                    try:
                        result[k] = json.loads(v)
                    except Exception:
                        items = [x.strip().strip("\"'") for x in v[1:-1].split(",") if x.strip()]
                        result[k] = items
                elif v.lower() == "true":
                    result[k] = True
                elif v.lower() == "false":
                    result[k] = False
                elif v.isdigit():
                    result[k] = int(v)
                else:
                    result[k] = v.strip("\"'")
    return result


def load_manifest(path: Path) -> dict:
    """读取并解析 plugin.yaml; 返回 dict。"""
    if not path.exists():
        raise FileNotFoundError(f"未找到清单: {path} (先运行 init)")
    content = path.read_text(encoding="utf-8")

    if HAS_PYYAML and yaml is not None:
        try:
            data = yaml.safe_load(content) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    # 降级使用内置解析器
    data = _simple_yaml_load(content)
    if not isinstance(data, dict):
        raise TypeError(f"{path} 不是合法的映射结构")
    return data


def dump_manifest(data: dict, path: Path) -> None:
    """写出 plugin.yaml。"""
    if HAS_PYYAML and yaml is not None:
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return

    # 降级纯文本格式化输出
    lines: list[str] = []
    for k, v in data.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for item in v:
                    if isinstance(item, dict):
                        first = True
                        for ik, iv in item.items():
                            if first:
                                lines.append(f"  - {ik}: {iv}")
                                first = False
                            else:
                                lines.append(f"    {ik}: {iv}")
                    else:
                        lines.append(f"  - {item}")
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for ik, iv in v.items():
                lines.append(f"  {ik}: {iv}")
        else:
            lines.append(f"{k}: {v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
