"""agentplatform CLI(006 §6):init / validate / dev / deploy / test / logs。

本地开发层不依赖远程平台;deploy 对接平台 /plugins/deploy。
入口:`python -m agentplatform.cli.main <cmd>` 或 uv 提供 agentplatform 命令。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from agentplatform.cli import yaml_io
from agentplatform.cli.validate import validate_project

TEMPLATE_PLUGIN_YAML = """\
name: {name}
version: 0.1.0
description: {name} 插件
author: ""
model: ""
depends_on: []
skills: []
tools: []
"""

TEMPLATE_SKILL = '''\
"""skill 示例(006 §3)。"""
from agentplatform.sdk import Skill, skill


@skill(id="skill:{name}_demo", version="0.1.0")
class DemoSkill(Skill):
    description = "示例 skill"
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    prompt = "请处理:{{text}}"

    def execute(self, ctx, args):
        return self.render(args)
'''

TEMPLATE_TOOL = '''\
"""tool 示例(006 §4)。"""
from agentplatform.sdk import tool


@tool(id="tool:{name}_echo", version="0.1.0")
def echo(text: str) -> str:
    """回显文本。"""
    return text
'''


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.name)
    if root.exists() and any(root.iterdir()):
        print(f"目录已存在且非空: {root}")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    (root / "skills").mkdir(exist_ok=True)
    (root / "tools").mkdir(exist_ok=True)
    yaml_io.dump_manifest(yaml.safe_load(
        TEMPLATE_PLUGIN_YAML.format(name=args.name)), root / "plugin.yaml")
    (root / "skills" / "demo.py").write_text(TEMPLATE_SKILL.format(name=args.name), encoding="utf-8")
    (root / "tools" / "demo.py").write_text(TEMPLATE_TOOL.format(name=args.name), encoding="utf-8")
    (root / "test").mkdir(exist_ok=True)
    print(f"已初始化插件项目: {root}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_project(Path(args.path))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def cmd_deploy(args: argparse.Namespace) -> int:
    """准入(006 §6.3):强制 validate;存在 test/ 则先跑 test。"""
    result = validate_project(Path(args.path))
    if not result["ok"]:
        print(json.dumps({"ok": False, "errors": result["errors"]}, ensure_ascii=False))
        return 1
    manifest = _build_manifest(Path(args.path), result["resources"])
    import httpx

    try:
        resp = httpx.post(
            f"{args.target.rstrip('/')}/api/plugins/deploy",
            json=manifest,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"部署失败(网络): {exc}")
        return 1
    if resp.status_code != 201:
        print(f"部署失败: {resp.status_code} {resp.text}")
        return 1
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    return 0


def _build_manifest(root: Path, resources: list[dict]) -> dict:
    raw = yaml_io.load_manifest(root / "plugin.yaml")
    by_kind: dict[str, list[dict]] = {"skill": [], "tool": []}
    for r in resources:
        by_kind[r["kind"]].append(
            {
                "id": r["id"],
                "file": r.get("file", ""),
                "description": r.get("description", ""),
                "schema": r.get("schema", {"type": "object", "properties": {}}),
            }
        )
    return {
        "name": raw.get("name"),
        "version": raw.get("version"),
        "description": raw.get("description"),
        "author": raw.get("author"),
        "model": raw.get("model"),
        "depends_on": raw.get("depends_on", []),
        "skills": by_kind["skill"],
        "tools": by_kind["tool"],
    }


def cmd_dev(args: argparse.Namespace) -> int:
    """本地对话调试(006 §6.1):复用 M5 agent 循环 + OpenAI 兼容本地端点。"""
    import asyncio
    import os

    from agentplatform.cli.dev import run_dev_loop

    base = os.environ.get("OPENAI_BASE_URL", "http://localhost:8001")
    key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("MODEL", "deepseek-v4-flash")
    asyncio.run(run_dev_loop(Path(args.path), base, key, model))
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """跑 test/*.yaml 用例(006 §6.2,基础版:校验 manifest 与资源可加载)。"""
    from agentplatform.cli.test_cases import run_tests

    return run_tests(Path(args.path))


def cmd_logs(args: argparse.Namespace) -> int:
    print("远程日志: 对接平台 /chat/sessions(待平台接入);本地 dev 会话请见 dev 输出。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentplatform", description="插件开发 CLI(006 §6)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="生成插件项目脚手架")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("validate", help="校验清单/依赖/命名空间(结构化输出)")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("dev", help="本地对话调试(不依赖远程平台)")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_dev)

    sp = sub.add_parser("test", help="跑 test/*.yaml 用例")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("deploy", help="部署到平台(强制准入 validate)")
    sp.add_argument("path", default=".", nargs="?")
    sp.add_argument("--target", required=True, help="平台地址,如 http://localhost:8001")
    sp.set_defaults(func=cmd_deploy)

    sp = sub.add_parser("logs", help="查看日志(预留)")
    sp.set_defaults(func=cmd_logs)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
