"""SDK 资源提取(设计 006 §3-4):从模块提取 skill/tool 元信息。

CLI validate / deploy 用:加载插件代码模块 -> 提取 @skill/@tool 注册的资源,
生成与平台注册表一致的结构化元信息(含 schema、impl 可调用)。
"""

from __future__ import annotations

from typing import Any

from agentplatform.sdk.decorators import as_skill_callable, as_tool_callable


def resources_from_module(module: Any) -> list[dict]:
    """提取模块内 @skill/@tool 注册的资源,返回平台格式元信息列表。"""
    out: list[dict] = []
    for entry in getattr(module, "__skill_registry__", []) or []:
        cls = entry["cls"]
        out.append(
            {
                "id": entry["id"],
                "kind": "skill",
                "version": entry["version"],
                "description": getattr(cls, "description", ""),
                "schema": getattr(cls, "schema", {"type": "object", "properties": {}}),
                "impl": as_skill_callable(cls),
            }
        )
    for entry in getattr(module, "__tool_registry__", []) or []:
        obj = entry["obj"]
        schema = getattr(obj, "schema", {"type": "object", "properties": {}})
        out.append(
            {
                "id": entry["id"],
                "kind": "tool",
                "version": entry["version"],
                "description": getattr(obj, "description", ""),
                "schema": schema,
                "impl": as_tool_callable(obj),
            }
        )
    return out


def load_resources(path: str) -> list[dict]:
    """按文件路径加载插件代码模块并提取资源(供 CLI/平台执行器复用)。"""
    import importlib.util

    module_name = f"agentplatform_plugin_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return resources_from_module(module)
