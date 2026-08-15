"""CLI validate(006 §6):清单/命名空间/资源结构校验,输出结构化结果。

强制项(006 §6.3 准入):name/version/命名空间前缀/depends_on 格式。
远程依赖校验(deploy 时)另行调用平台 /registry。
"""

from __future__ import annotations

from pathlib import Path

from agentplatform.core.plugin.manifest import (
    PluginManifest,
    validate_manifest as _validate_structure,
)
from agentplatform.sdk.loader import load_resources



def validate_project(root: Path) -> dict:
    """校验插件项目,返回结构化结果 {ok, errors[], resources[]}。"""
    errors: list[str] = []
    try:
        manifest_path = root / "plugin.yaml"
        if not manifest_path.exists():
            return {"ok": False, "errors": [f"缺少 plugin.yaml 清单文件: {manifest_path.name}"], "resources": []}

        raw = _load_manifest_safe(manifest_path)
        if raw is None or not isinstance(raw, dict):
            return {"ok": False, "errors": ["plugin.yaml 解析失败或内容格式不合法"], "resources": []}

        try:
            manifest = PluginManifest(**raw)
            _validate_structure(manifest)
        except Exception as exc:  # noqa: BLE001  收集所有校验错误
            errors.append(f"清单格式错误: {exc}")

        # 命名空间:skill id 以 skill: 开头、tool id 以 tool: 开头(006 §3/§4)
        for section in ("skills", "tools"):
            for res in raw.get(section, []) or []:
                if not isinstance(res, dict):
                    errors.append(f"{section} 列表项必须为对象字典")
                    continue
                rid = res.get("id", "")
                prefix = "skill:" if section == "skills" else "tool:"
                if not rid.startswith(prefix):
                    errors.append(f"{section} 资源 id 必须以 {prefix!r} 开头: {rid!r}")
                if not res.get("file"):
                    errors.append(f"{section} 资源缺 file 属性: {rid!r}")

        # depends_on 格式校验
        for dep in raw.get("depends_on", []) or []:
            if not isinstance(dep, str) or "@" not in dep:
                errors.append(f"depends_on 依赖项格式错误(建议带版本约束如 tool:pdf_parse@^1.0): {dep!r}")

        # 从代码提取资源元信息(含 schema)
        resources: list[dict] = []
        for section in ("skills", "tools"):
            for res in raw.get(section, []) or []:
                if not isinstance(res, dict) or not res.get("file"):
                    continue
                f = root / res.get("file", "")
                if not f.exists():
                    errors.append(f"资源实现文件不存在: {res.get('file')}")
                    continue
                try:
                    loaded = load_resources(str(f))
                    matching = [r for r in loaded if r["id"] == res.get("id")]
                    if not matching:
                        errors.append(f"文件 {res.get('file')} 中未找到被 @{section[:-1]} 装饰的资源 id={res.get('id')!r}")
                    else:
                        for m in matching:
                            item = {k: v for k, v in m.items() if k != "impl"}
                            item["file"] = str((root / res.get("file", "")).resolve())
                            resources.append(item)
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"解析资源 {res.get('id')} 失败 ({res.get('file')}): {exc}")


        return {"ok": not errors, "errors": errors, "resources": resources}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"插件校验发生未预期异常: {exc}"], "resources": []}



def _load_manifest_safe(path: Path) -> dict | None:
    from agentplatform.cli.yaml_io import load_manifest

    try:
        return load_manifest(path)
    except Exception:  # noqa: BLE001
        return None
