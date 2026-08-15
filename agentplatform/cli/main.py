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
    schema = {{"type": "object", "properties": {{"text": {{"type": "string"}}}}, "required": ["text"]}}
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


TEMPLATE_AGENTS_MD = """\
# 🤖 AgentPlatform 智能体插件开发指南 (针对 AI Assistant / Claude Code / Cursor)

你当前位于一个 **AgentPlatform 智能体插件工程** 中。你的任务是协助开发者设计、实现、测试与部署这个专属领域智能体助手。

---

## ⚠️ 架构红线与开发边界约束 (CRITICAL BOUNDARIES)
1. **工作区边界严格隔离**：
   - 你的所有工作（代码编写、单测、调试、文件修改）必须且只能在**当前插件工程目录**内进行。
   - **严禁**搜索、读取、修改或打补丁到外部平台源码目录（如平台后端或 SDK 源码）。
2. **SDK 作为标准只读依赖**：
   - 平台 SDK (`agentplatform.sdk`) 为外部只读依赖，直接从全局环境或 `site-packages` 导入。
   - 严禁尝试在插件环境安装平台服务端底层依赖（如 `sqlalchemy`, `asyncpg`, `alembic`, `fastapi`, `redis` 等）。
3. **闭环自愈原则**：
   - 若 `agentplatform validate` 或测试报错，请根据结构化 JSON 提示原地检查并修正插件内的 `plugin.yaml`、参数 `schema` 或实现代码，直至全部通过。

---

## 1. 平台公共内置能力 (可在 plugin.yaml 的 depends_on 中直接复用)
无需自行重复编写底层解析与算法，平台已内置高稳定性的基础工具与技能：
- `tool:pdf_parse@^1.0` : 确定性 PDF 文件文本与结构解析提取
- `skill:summarize@^1.0` : 针对长文本/文档的多维度核心摘要提取
- `skill:structured_output@^1.0` : 结构化 JSON 数据抽取与字段规范化

---

## 2. 插件工程架构规范
- `plugin.yaml` : 核心清单，声明插件名称、模型、版本、公共依赖 (depends_on)、自有 skills 与 tools。
- `skills/` : 编写 Prompt 模板与思考能力的技能。使用 `@skill(id="...", version="...")` 装饰。
- `tools/` : 编写纯确定性 Python 计算/数据处理逻辑。使用 `@tool(id="...", version="...")` 装饰。
- `test/` : 存放单元测试 (`test_*.py` 供 pytest) 与自动化用例 (`*.yaml` 供 `agentplatform test`)。

---

## 3. 22 种富交互组件 (ContentBlocks) 输出
如果希望智能体在前端 Web 界面呈现富交互效果，可让模型调用特殊工具 `output_block({{type, data, meta}})`：
- **展示类 (8)**: `markdown`, `code` (带高亮与复制), `table` (可排序列), `card` (嵌套卡片), `collapsible` (折叠面板), `image` (安全放大预览), `file` (附件下载), `mermaid` (图表).
- **交互输入类 (11)**: `input.text`, `input.textarea`, `input.number`, `input.select`, `input.radio`, `input.checkbox`, `input.toggle`, `input.date`, `input.file`, `input.confirm` (确认/取消动作), `input.form` (多字段组合表单).
- **反馈动作类 (3)**: `action.copy`, `action.thumbs` (点赞点踩), `action.regenerate`.

---

## 4. 你的标准自愈开发流水线
每当你生成或修改代码后，请按序执行以下命令验证：
1. **单元测试**: `pytest` (测试 tools/skills 内部 Python 逻辑)
2. **静态校验**: `agentplatform validate .`
   - 若返回 `errors`，根据报错 JSON 原地修正代码，直至 `ok: true`。
3. **用例测试**: `agentplatform test .`
4. **本地对话冒烟**: `agentplatform dev .`
5. **一键部署发布**: `agentplatform deploy . --target http://localhost:8000`

---

## 5. 本地人肉测试与双模式工作流规范 (LOCAL HUMAN TESTING PROTOCOL)
1. **用户模拟测试模式 (User Roleplay / 人肉测试)**：
   - 触发暗号：当开发者说「我来测」、「开始测试」、「人肉测试」或直接发送普通业务指令时。
   - 核心行为：
     1. 立即进入本插件专属的智能体角色（Persona）；
     2. 在后台静默调用 `agentplatform chat "<用户输入>"` 或静默调用本地 tools/skills，**严禁输出任何 bash 命令、Python 代码片段或调试日志**；
     3. 自动维持多轮会话记忆（继承前序参数与上下文）；
     4. 完全以面向终端用户的自然口吻输出最终助手的 Markdown 回答与图表；
     5. 严禁向用户暴露底层插件配置、示例断言或代码实现。
2. **开发者模式 (Developer Mode)**：
   - 触发暗号：当开发者说「切回开发」、「改代码」、「修 bug」或提出代码修改需求时。
   - 行为要求：恢复为资深研发伙伴，协助开发者分析代码、编写单测、修复 Bug 并执行 validate。
"""





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
    (root / "AGENTS.md").write_text(TEMPLATE_AGENTS_MD.format(name=args.name), encoding="utf-8")
    (root / "CLAUDE.md").write_text(TEMPLATE_AGENTS_MD.format(name=args.name), encoding="utf-8")
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
            f"{args.target.rstrip('/')}/api/plugins/deploy?overwrite=true",
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
    """本地对话调试(006 §6.1):复用 M5 agent 循环 + OpenAI 兼容端点。"""
    import asyncio
    import os

    from agentplatform.cli.dev import run_dev_loop
    from agentplatform.config import settings

    base = os.environ.get("OPENAI_BASE_URL") or settings.openai_base_url or "https://api.eaglesine.com/v1"
    key = os.environ.get("OPENAI_API_KEY") or settings.openai_api_key
    model = os.environ.get("MODEL") or settings.default_model or "DeepSeek-V3"

    if not key or key == "dev":
        print("\n❌ 错误: 未检测到有效 OPENAI_API_KEY。")
        print("请在系统环境变量中设置: export OPENAI_API_KEY=\"sk-...\"")
        print("或在项目根目录 / ~/.agentplatform/.env 中写入: OPENAI_API_KEY=sk-...\n")
        return 1

    asyncio.run(run_dev_loop(Path(args.path), base, key, model))
    return 0




def cmd_chat(args: argparse.Namespace) -> int:
    """单轮/多轮本地对话执行(人肉测试模式后台调用)。"""
    import asyncio
    from agentplatform.cli.chat import run_single_chat

    reply = asyncio.run(
        run_single_chat(
            root=Path(args.path),
            message=args.message or "",
            reset=args.reset,
        )
    )
    print(reply)
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    """跑 test/*.yaml 用例(006 §6.2,基础版:校验 manifest 与资源可加载)。"""
    from agentplatform.cli.test_cases import run_tests

    return run_tests(Path(args.path))


def cmd_update(args: argparse.Namespace) -> int:
    """一键同步/升级插件项目的标准规范与协议文件 (AGENTS.md / CLAUDE.md)，支持拉取新包与远程规范。"""
    import subprocess
    import sys
    import httpx

    root = Path(args.path)
    manifest_path = root / "plugin.yaml"
    if not manifest_path.exists():
        print(f"错误: 目录中未找到 plugin.yaml: {root}")
        return 1

    try:
        raw = yaml_io.load_manifest(manifest_path)
        name = raw.get("name", "plugin")
    except Exception:
        name = "plugin"

    # 1. 如果指定了 --package，自动通过 pip 拉取/升级最新的 agentplatform 包
    if getattr(args, "package", False):
        print("📦 正在拉取升级 agentplatform 最新软件包...")
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "agentplatform"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                print("✅ 软件包已升级到最新版本！")
            else:
                print(f"提示: pip 升级输出: {proc.stderr.strip() or proc.stdout.strip()}")
        except Exception as exc:
            print(f"提示: 尝试自动升级包失败 ({exc})，建议运行 pip install -U agentplatform")

    # 2. 如果指定了 --target，从远程平台服务器拉取最新规范模板
    content = TEMPLATE_AGENTS_MD
    if getattr(args, "target", None):
        target_url = f"{args.target.rstrip('/')}/api/specs/agents-md"
        print(f"🌐 正在从远程平台拉取最新规范 ({target_url})...")
        try:
            resp = httpx.get(target_url, timeout=10)
            if resp.status_code == 200:
                content = resp.json().get("template_agents_md", TEMPLATE_AGENTS_MD)
                print(f"✅ 成功获取远程规范模版 (v{resp.json().get('version', 'latest')})")
            else:
                print(f"警告: 远程获取失败 ({resp.status_code})，使用本地内置最新规范。")
        except Exception as exc:
            print(f"警告: 连接远程平台失败 ({exc})，使用本地内置最新规范。")

    # 3. 刷新写入本地 CLAUDE.md 与 AGENTS.md
    formatted_content = content.format(name=name)
    (root / "AGENTS.md").write_text(formatted_content, encoding="utf-8")
    (root / "CLAUDE.md").write_text(formatted_content, encoding="utf-8")
    print(f"✅ 插件工程规范已同步就绪！")
    print(f"  - 已更新: {root / 'AGENTS.md'}")
    print(f"  - 已更新: {root / 'CLAUDE.md'}")
    print(f"  - 已生效: 【本地人肉测试协议 (我来测/开始测试)】与【双模式自动切换】")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    print("远程日志: 对接平台 /chat/sessions(待平台接入);本地 dev 会话请见 dev 输出。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentplatform", description="插件开发 CLI(006 §6)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="生成插件项目脚手架")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("update", help="一键同步/升级插件项目规范与协议(AGENTS.md / CLAUDE.md)")
    sp.add_argument("path", default=".", nargs="?")
    sp.add_argument("--package", action="store_true", help="同时拉取并升级本地 agentplatform Python 软件包")
    sp.add_argument("--target", default=None, help="远程平台服务器地址，如 http://localhost:8000")
    sp.set_defaults(func=cmd_update)


    sp = sub.add_parser("validate", help="校验清单/依赖/命名空间(结构化输出)")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("dev", help="本地交互式对话调试(REPL)")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_dev)

    sp = sub.add_parser("chat", help="本地单句/多轮对话(人肉测试专用)")
    sp.add_argument("message", nargs="?", default="", help="用户输入消息")
    sp.add_argument("--path", default=".", help="插件工程目录")
    sp.add_argument("--reset", action="store_true", help="重置当前本地多轮会话历史")
    sp.set_defaults(func=cmd_chat)

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
