"""CLI test(006 §6.2):跑 test/*.yaml 用例,输出结构化结果。

MVP 形态:每例校验 manifest 可解析 + 资源可加载 + 可选断言(见 006 §6.2 示例)。
完整 agent 运行断言留 T10.1 联调。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from agentplatform.cli.validate import validate_project


def run_tests(root: Path) -> int:
    results: list[dict] = []
    cases_dir = root / "test"
    if not cases_dir.exists():
        print(json.dumps({"ok": True, "cases": [], "note": "无 test/ 目录"}, ensure_ascii=False))
        return 0

    base = validate_project(root)
    for case_file in sorted(cases_dir.glob("*.yaml")):
        result = _run_case(case_file, base)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False))

    ok = all(r["ok"] for r in results)
    return 0 if ok else 1


def _run_case(case_file: Path, base: dict) -> dict:
    try:
        case = yaml.safe_load(case_file.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        return {"name": case_file.stem, "ok": False, "errors": [f"解析失败: {exc}"]}

    name = case.get("name", case_file.stem)
    errors: list[str] = []
    if not base["ok"]:
        errors.extend(base["errors"])
    expect = case.get("expect", {}) or {}
    tool_calls = expect.get("tool_calls", [])
    for rid in tool_calls:
        if not any(r["id"] == rid for r in base.get("resources", [])):
            errors.append(f"期望调用 {rid} 未在插件资源中找到")
    output_contains = expect.get("output_contains", [])
    for s in output_contains:
        if s and not case.get("input", ""):  # MVP 仅校验用例结构完整性
            errors.append(f"断言 {s!r} 需要 input")
    return {"name": name, "ok": not errors, "errors": errors}
