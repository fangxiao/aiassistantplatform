"""agentplatform CLI(006 §6): init / validate / dev / deploy / test / logs / registry / widgets / guide。

本地开发层不依赖远程平台; deploy 对接平台 /plugins/deploy。
入口: `python -m agentplatform.cli.main <cmd>` 或 uv 提供 agentplatform 命令。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from agentplatform.cli import yaml_io
from agentplatform.cli.validate import validate_project
from agentplatform.core.registry.capabilities import CONTENT_BLOCKS_CATALOG, get_capabilities_manifest

TEMPLATE_PLUGIN_YAML = """\
# 🤖 AgentPlatform 插件清单 (006 §2)
# 插件即专属 AI 助手，可复用平台公共 Skill/Tool 与 22 种富交互组件。
name: {name}
version: 0.1.0
description: {name} 智能体助手
author: Developer
model: deepseek-v4-flash  # 或已配置的其他大语言模型端点

# 🌟 第一特色：平台共享能力复用 (支持 ^/~ SemVer 版本约束)
# 可直接声明依赖平台公共内置能力，无需重复造轮子：
#   - tool:pdf_parse@^1.0        # 确定性 PDF 解析提取文本
#   - skill:summarize@^1.0       # 智能多维度长文本摘要
#   - skill:structured_output@^1.0 # 结构化 JSON 字段提取
depends_on:
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0

# 声明本插件自有 Skill (技能：含领域 Prompt 模板与参数渲染)
skills:
  - id: skill:{name}_demo
    file: ./skills/demo.py

# 声明本插件自有 Tool (工具：确定性计算与接口调用)
tools:
  - id: tool:{name}_echo
    file: ./tools/demo.py
"""

TEMPLATE_SKILL = '''\
\"\"\"插件领域技能定义 (Skill)。

Skill 负责将领域知识、Prompt 模板与上下文结合。
可以在 execute 中处理参数并渲染模板，或直接构建结构化提示。
\"\"\"
from typing import Any
from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:{name}_demo",
    version="0.1.0",
    description="示例领域技能：智能分析与结构化建议输出",
    schema={{
        "type": "object",
        "properties": {{
            "query": {{"type": "string", "description": "用户输入的咨询或分析需求"}},
            "tone": {{
                "type": "string",
                "enum": ["professional", "creative"],
                "description": "输出语气风格",
            }},
        }},
        "required": ["query"],
    }},
    prompt="你是一个领域专家，请以 {{{{tone}}}} 风格针对以下内容提供专业分析：\\n{{{{query}}}}",
)
class DemoSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        if not args.get("tone"):
            args["tone"] = "professional"
        return self.render(args)
'''

TEMPLATE_TOOL = '''\
\"\"\"插件确定性工具定义 (Tool)。

Tool 负责执行确定性 Python 计算、格式转换或外部接口调用。
\"\"\"
import json
from agentplatform.sdk import tool


@tool(
    id="tool:{name}_echo",
    version="0.1.0",
    description="回显与简单格式化工具",
    schema={{
        "type": "object",
        "properties": {{
            "text": {{"type": "string", "description": "输入文本"}},
        }},
        "required": ["text"],
    }},
)
def echo(text: str) -> str:
    """回显输入的文本并包装状态。"""
    return json.dumps({{"status": "success", "echo": text}}, ensure_ascii=False)
'''

TEMPLATE_TEST_CASES_YAML = """\
# 自动化测试用例 (供 agentplatform test 执行)
tests:
  - name: "基础功能验证"
    input: "你好，请介绍你的功能"
    expect_contains: []
"""

TEMPLATE_CURSORRULES = """\
# AgentPlatform AI 插件开发规范 (Cursor / Windsurf 专配)
- 你正在开发一个 AgentPlatform 智能体插件。
- 平台第一特色：复用平台公共 Skill (`skill:summarize`, `skill:structured_output`) 和 Tool (`tool:pdf_parse`)，在 plugin.yaml 的 depends_on 声明。
- 平台控件能力：模型可通过 output_block 工具输出 22 种富交互控件（Markdown, Table, Card, Collapsible, Mermaid, input.form, input.confirm, input.select 等）。
- 开发自愈流水线：
  1. 校验清单：agentplatform validate .
  2. 运行测试：agentplatform test .
  3. 本地调试：agentplatform dev .
  4. 部署平台：agentplatform deploy . --target http://localhost:8000
"""

TEMPLATE_AGENTS_MD = """\
# 🤖 AgentPlatform 智能体插件开发指南 (针对 AI Assistant / Claude Code / Antigravity / Cursor)

你当前位于一个 **AgentPlatform 智能体插件工程** 中。你的任务是协助开发者设计、实现、测试与部署这个专属领域智能体助手。

---

## ⚠️ 架构红线与开发边界约束 (CRITICAL BOUNDARIES)
1. **工作区边界严格隔离**：
    - 你的所有工作（代码编写、单测、调试、文件修改）必须且只能在**当前插件工程目录**内进行。
    - **严禁**搜索、读取、修改或打补丁到外部平台源码目录（如平台后端或 SDK 源码），也**严禁**对外部平台源码执行 `git pull` 或 git 操作。
    - 平台与插件是完全解耦的 Client-Server 架构：平台作为远端 HTTP 服务提供 API 与包下载。
 2. **SDK 与 CLI 依赖管理**：
    - 插件环境所需轻量依赖为 `agentplatform`（含 SDK 与 CLI）+ `pyyaml` + `pytest`。
    - 严禁在插件环境安装平台服务端底层数据库/网关依赖（如 `sqlalchemy`, `asyncpg`, `alembic`, `fastapi`, `redis` 等）。
 3. **闭环自愈原则**：
    - 若 `agentplatform validate` 或测试报错，请根据结构化 JSON 提示原地检查并修正插件内的 `plugin.yaml`、参数 `schema` 或实现代码，直至全部通过。

---

## 1. 平台公共内置能力 (可在 plugin.yaml 的 depends_on 中直接复用)
无需自行重复编写底层解析与算法，平台已内置高稳定性的基础工具与技能：
- `tool:pdf_parse@^1.0` : 确定性 PDF 文件文本与结构解析提取 (输入: `file_path`)
- `skill:summarize@^1.0` : 针对长文本/文档的多维度核心摘要提取 (参数: `text`, `style`, `max_words`)
- `skill:structured_output@^1.0` : 结构化 JSON 数据抽取与字段规范化 (参数: `text`, `schema_desc`)

**依赖声明语法示例 (`plugin.yaml`)**：
```yaml
depends_on:
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0
  - skill:structured_output@^1.0
```

---

## 2. 插件工程架构规范
- `plugin.yaml` : 核心清单，声明插件名称、模型、版本、公共依赖 (`depends_on`)、自有 skills 与 tools。
- `pyproject.toml` : 插件工程轻量依赖配置 (`agentplatform`, `pyyaml`, `pytest`)。
- `skills/` : 编写 Prompt 模板与思考能力的技能。使用 `@skill(id="skill:...", version="...")` 装饰。
- `tools/` : 编写纯确定性 Python 计算/数据处理逻辑。使用 `@tool(id="tool:...", version="...")` 装饰。
- `test/` : 存放单元测试 (`test_*.py` 供 pytest) 与自动化用例 (`test_cases.yaml` 供 `agentplatform test`)。

---

## 3. 22 种富交互组件 (ContentBlocks) 输出
如果希望智能体在前端 Web 界面呈现富交互效果，可让模型调用特殊工具 `output_block({{type, data, meta}})`：
- **展示类 (8)**:
  - `markdown` (富文本), `code` (代码高亮带复制), `table` (多列排序表格), `card` (卡片容器), `collapsible` (折叠面板), `image` (安全图片预览), `file` (文件下载条目), `mermaid` (图表流程图).
- **交互输入类 (11)**:
  - `input.text` (单行输入), `input.textarea` (多行文本), `input.number` (数字输入), `input.select` (下拉选择), `input.radio` (单选组), `input.checkbox` (多选组), `input.toggle` (开关), `input.date` (日期), `input.file` (文件上传), `input.confirm` (确认操作框), `input.form` (复合表单).
- **反馈动作类 (3)**:
  - `action.copy` (一键复制文本), `action.thumbs` (点赞点踩打标), `action.regenerate` (重新生成动作).

**示例：输出交互式确认与表单控件**
```json
{{
  "type": "input.confirm",
  "data": {{
    "text": "是否确认将该 PRD 评审报告导出为 PDF 格式？",
    "action": "export_pdf_confirm",
    "confirm_text": "确认导出",
    "cancel_text": "稍后再说"
  }}
}}
```

---

## 4. 你的标准自愈开发流水线
每当你生成或修改代码后，请按序执行以下命令验证：
1. **单元测试**: `pytest` (测试 tools/skills 内部 Python 逻辑)
2. **静态校验**: `agentplatform validate .`
   - 若返回 `errors`，根据报错 JSON 原地修正代码，直至 `ok: true`。
3. **用例测试**: `agentplatform test .`
4. **查阅共享资源**: `agentplatform registry`
5. **查阅可用控件**: `agentplatform widgets`
6. **本地对话冒烟**: `agentplatform dev .`
7. **一键部署发布**: `agentplatform deploy .`

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

---

## 6. 自然语言一键远程升级指令 (REMOTE AUTO-UPGRADE DIRECTIVE)
- 当开发者说「远程更新平台 CLI」、「更新 CLI」、「升级平台」、「同步规范」或「更新一下」时：
  1. **严禁** 去外部平台源码目录执行 git pull 或查看平台 git 状态！
  2. **严禁** 弹出多选菜单或询问打断用户！
  3. **立即在后台直接执行命令**：`agentplatform update`；
     （若提示找不到 agentplatform 命令，则执行：`pip install --upgrade http://localhost:8000/api/specs/package.tar.gz && agentplatform update`）
  4. 该命令会自动通过 HTTP 从远程平台服务器拉取最新 SDK 代码包与规范；
  5. 执行完毕后向开发者回复简短确认。
"""


TEMPLATE_PLUGIN_PYPROJECT_TOML = """\
[project]
name = "{name}"
version = "0.1.0"
description = "{name} - AgentPlatform 智能体插件"
requires-python = ">=3.10"
dependencies = [
    "agentplatform>=0.1.0",
    "pyyaml>=6.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
"""


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.name)
    if root.exists() and any(root.iterdir()):
        print(f"目录已存在且非空: {root}")
        return 1
    root.mkdir(parents=True, exist_ok=True)
    (root / "skills").mkdir(exist_ok=True)
    (root / "tools").mkdir(exist_ok=True)
    (root / "test").mkdir(exist_ok=True)
    (root / ".agents" / "skills" / "agentplatform-plugin-dev").mkdir(parents=True, exist_ok=True)

    plugin_name = Path(args.name).name
    yaml_io.dump_manifest(
        yaml_io.load_manifest(Path("dummy")) if False else {
            "name": plugin_name,
            "version": "0.1.0",
            "description": f"{plugin_name} 智能体助手",
            "author": "Developer",
            "model": "deepseek-v4-flash",
            "depends_on": ["tool:pdf_parse@^1.0", "skill:summarize@^1.0"],
            "skills": [{"id": f"skill:{plugin_name}_demo", "file": "./skills/demo.py"}],
            "tools": [{"id": f"tool:{plugin_name}_echo", "file": "./tools/demo.py"}],
        },
        root / "plugin.yaml",
    )
    (root / "skills" / "demo.py").write_text(TEMPLATE_SKILL.format(name=plugin_name), encoding="utf-8")
    (root / "tools" / "demo.py").write_text(TEMPLATE_TOOL.format(name=plugin_name), encoding="utf-8")
    (root / "test" / "test_cases.yaml").write_text(TEMPLATE_TEST_CASES_YAML, encoding="utf-8")
    (root / "pyproject.toml").write_text(TEMPLATE_PLUGIN_PYPROJECT_TOML.format(name=plugin_name), encoding="utf-8")

    agents_content = TEMPLATE_AGENTS_MD.format(name=plugin_name)
    (root / "AGENTS.md").write_text(agents_content, encoding="utf-8")
    (root / "CLAUDE.md").write_text(agents_content, encoding="utf-8")
    (root / ".cursorrules").write_text(TEMPLATE_CURSORRULES, encoding="utf-8")
    (root / ".agents" / "skills" / "agentplatform-plugin-dev" / "SKILL.md").write_text(
        f"---\nname: agentplatform-plugin-dev\ndescription: AgentPlatform 插件开发与共享能力指南\n---\n\n{agents_content}",
        encoding="utf-8",
    )

    print(f"🎉 已成功初始化 AgentPlatform 插件脚手架: {root}")
    print("📁 生成文件清单:")
    print("  ├── plugin.yaml       # 插件清单 (已配置共享能力 depends_on 示例)")
    print("  ├── pyproject.toml    # 插件轻量依赖声明 (agentplatform, pyyaml, pytest)")
    print("  ├── skills/demo.py    # 示例 Skill 技能 (含 Prompt 与参数)")
    print("  ├── tools/demo.py     # 示例 Tool 工具 (确定性计算与接口)")
    print("  ├── test/test_cases.yaml # 自动化测试用例")
    print("  ├── AGENTS.md / CLAUDE.md / .cursorrules # 全套 AI 编程助手支持规范")
    print("  └── .agents/skills/   # Antigravity / Gemini 专属插件开发 Skill")
    print("\n💡 常用开发命令:")
    print(f"  cd {args.name}")
    print("  agentplatform registry   # 查看平台可复用的公共 Skill/Tool")
    print("  agentplatform widgets    # 查看可输出的 22 种富交互控件")
    print("  agentplatform validate . # 校验规范")
    print("  agentplatform dev .      # 本地交互式调试")
    return 0


def get_target_url(args: argparse.Namespace | None = None) -> str:
    """获取平台服务器地址 (优先级: --target 参数 > AGENTPLATFORM_TARGET 环境变量 > ~/.agentplatform/config.json > 默认 http://localhost:8000)。"""
    if args and getattr(args, "target", None):
        return args.target.rstrip("/")
    import os

    env_target = os.environ.get("AGENTPLATFORM_TARGET")
    if env_target:
        return env_target.rstrip("/")

    try:
        user_cfg = Path.home() / ".agentplatform" / "config.json"
        if user_cfg.exists():
            cfg = json.loads(user_cfg.read_text(encoding="utf-8"))
            if cfg.get("target"):
                return cfg["target"].rstrip("/")
    except Exception:
        pass

    return "http://localhost:8000"


def cmd_registry(args: argparse.Namespace) -> int:
    """查阅平台公共内置/共享技能与工具注册表 (默认优先从远程平台服务实时获取)。"""
    target = get_target_url(args)
    manifest = None

    # 优先尝试从远程平台服务拉取实时注册表 (跨机器支持)
    if target:
        try:
            import httpx

            resp = httpx.get(f"{target}/api/specs/capabilities", timeout=5)
            if resp.status_code == 200:
                manifest = resp.json()
        except Exception:
            pass

    if manifest is None:
        manifest = get_capabilities_manifest()

    if getattr(args, "json", False):
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    print("================================================================================")
    print("📚 AgentPlatform 平台共享能力注册表 (Skill & Tool Registry)")
    print("================================================================================")
    print(f"🌐 平台源: {target} (已连接)" if manifest.get("platform") else "💡 本地内置离线模式")
    print("💡 平台第一特色：以下公共技能与工具无需重复编写，可在 plugin.yaml 的 depends_on 中直接声明复用！\n")

    print("🔧 公共工具 (Built-in Tools):")
    print("--------------------------------------------------------------------------------")
    for t in manifest["builtin_tools"]:
        print(f"• ID: {t['id']}  (v{t['version']})")
        print(f"  描述: {t['description']}")
        print(f"  依赖声明: {t['dependency_example']}")
        params = t.get("schema", {}).get("parameters", {}).get("properties", {})
        if params:
            props_str = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in params.items())
            print(f"  输入参数: {props_str}")
        print()

    print("🧠 公共技能 (Built-in Skills):")
    print("--------------------------------------------------------------------------------")
    for s in manifest["builtin_skills"]:
        print(f"• ID: {s['id']}  (v{s['version']})")
        print(f"  描述: {s['description']}")
        print(f"  依赖声明: {s['dependency_example']}")
        params = s.get("schema", {}).get("parameters", {}).get("properties", {})
        if params:
            props_str = ", ".join(f"{k}: {v.get('type', 'any')}" for k, v in params.items())
            print(f"  输入参数: {props_str}")
        print()

    print("👉 提示: 使用 `agentplatform registry --json` 可输出完整 JSON Schema。")
    return 0


def cmd_widgets(args: argparse.Namespace) -> int:
    """查阅平台 22 种富交互 ContentBlock 控件清单与调用样例。"""
    cat_filter = getattr(args, "category", None)
    blocks = CONTENT_BLOCKS_CATALOG
    if cat_filter:
        blocks = [b for b in blocks if b["category"] == cat_filter]

    if getattr(args, "json", False):
        print(json.dumps(blocks, ensure_ascii=False, indent=2))
        return 0

    print("================================================================================")
    print(f"🎨 AgentPlatform 22 种富交互组件画廊 (ContentBlocks, 共 {len(blocks)} 个)")
    print("================================================================================")
    print("💡 智能体可通过 output_block({type, data}) 输出富交互 UI，彻底超越传统纯文本对话！\n")

    current_cat = ""
    for b in blocks:
        if b["category_name"] != current_cat:
            current_cat = b["category_name"]
            print(f"\n【{current_cat}】")
            print("--------------------------------------------------------------------------------")
        print(f"• 类型: {b['type']}  ({b['name']})")
        print(f"  说明: {b['description']}")
        print(f"  调用示例: {b['python_snippet']}")
        print()

    print("👉 提示: 使用 `agentplatform widgets --json` 或访问 Web 开发者中心可体验交互预览。")
    return 0


def cmd_guide(args: argparse.Namespace) -> int:
    """查看完整的 AgentPlatform 开发者与 AI 协同指南。"""
    print(TEMPLATE_AGENTS_MD.format(name="my-assistant"))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    result = validate_project(Path(args.path))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _build_manifest(root: Path, resources: list[dict]) -> dict:
    raw = yaml_io.load_manifest(root / "plugin.yaml")
    by_kind: dict[str, list[dict]] = {"skill": [], "tool": []}
    for r in resources:
        file_path_str = r.get("file", "")
        code_content: str | None = None
        if file_path_str:
            p = Path(file_path_str) if Path(file_path_str).is_absolute() else (root / file_path_str)
            if p.exists() and p.is_file():
                try:
                    code_content = p.read_text(encoding="utf-8")
                except Exception:
                    pass

        by_kind[r["kind"]].append(
            {
                "id": r["id"],
                "file": file_path_str,
                "code": code_content,
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
        print('请在系统环境变量中设置: export OPENAI_API_KEY="sk-..."')
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


def cmd_deploy(args: argparse.Namespace) -> int:
    """准入(006 §6.3): 强制 validate; 存在 test/ 则先跑 test; 部署到远程平台服务。"""
    target = get_target_url(args)
    result = validate_project(Path(args.path))
    if not result["ok"]:
        print(json.dumps({"ok": False, "errors": result["errors"]}, ensure_ascii=False))
        return 1
    manifest = _build_manifest(Path(args.path), result["resources"])
    import httpx

    print(f"🚀 正在向平台服务部署插件 ({target}/api/plugins/deploy)...")
    try:
        resp = httpx.post(
            f"{target}/api/plugins/deploy?overwrite=true",
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
    print(f"🎉 插件 {manifest['name']}@{manifest['version']} 部署成功！可在 {target}/assistants 查验使用。")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """一键从远程平台服务同步/升级插件项目的标准规范、SDK 包与协议文件 (默认跨机器远程同步)。"""
    import os
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

    target = get_target_url(args)
    print(f"🌐 目标平台服务端: {target}")

    # 1. 默认自动从远程平台拉取并升级最新 live 代码包 (除非指定 --no-package)
    if not getattr(args, "no_package", False):
        pkg_url = f"{target}/api/specs/package.tar.gz"
        print(f"📦 正在直接从远程平台服务拉取最新 live SDK 软件包 ({pkg_url})...")
        try:
            import tempfile

            resp = httpx.get(pkg_url, timeout=30)
            if resp.status_code == 200:
                with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
                    tf.write(resp.content)
                    tmp_path = tf.name

                installed = False
                # 依次尝试 uv pip / python -m pip / pip
                for cmd in [
                    ["uv", "pip", "install", "--upgrade", tmp_path],
                    [sys.executable, "-m", "pip", "install", "--upgrade", tmp_path],
                    ["pip", "install", "--upgrade", tmp_path],
                ]:
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
                        if proc.returncode == 0:
                            installed = True
                            print("✅ 已从远程平台成功安装最新 SDK 代码包！")
                            break
                    except FileNotFoundError:
                        continue

                if not installed:
                    print(f"💡 提示: 自动包安装已就绪。如需升级环境，可手动运行: uv pip install {pkg_url}")
            else:
                print(f"提示: 远程平台未返回包 ({resp.status_code})，跳过 SDK 升级。")
        except Exception as exc:
            print(f"提示: 远程平台包下载异常 ({exc})，跳过 SDK 升级。")

    # 2. 从远程平台服务器拉取最新规范模板
    content = TEMPLATE_AGENTS_MD
    target_url = f"{target}/api/specs/agents-md"
    print(f"📄 正在从远程平台拉取最新规范模板 ({target_url})...")
    try:
        resp = httpx.get(target_url, timeout=10)
        if resp.status_code == 200:
            content = resp.json().get("template_agents_md", TEMPLATE_AGENTS_MD)
            print(f"✅ 成功获取远程规范模版 (v{resp.json().get('version', 'latest')})")
        else:
            print(f"警告: 远程获取失败 ({resp.status_code})，使用本地内置最新规范。")
    except Exception as exc:
        print(f"警告: 连接远程平台失败 ({exc})，使用本地内置最新规范。")

    # 3. 刷新写入本地 CLAUDE.md、AGENTS.md、.cursorrules、pyproject.toml 与 .agents 技能
    formatted_content = content.format(name=name)
    (root / "AGENTS.md").write_text(formatted_content, encoding="utf-8")
    (root / "CLAUDE.md").write_text(formatted_content, encoding="utf-8")
    (root / ".cursorrules").write_text(TEMPLATE_CURSORRULES, encoding="utf-8")

    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        pyproject_path.write_text(TEMPLATE_PLUGIN_PYPROJECT_TOML.format(name=name), encoding="utf-8")
        print(f"  - 已补齐: {pyproject_path}")

    agents_skill_dir = root / ".agents" / "skills" / "agentplatform-plugin-dev"
    agents_skill_dir.mkdir(parents=True, exist_ok=True)
    (agents_skill_dir / "SKILL.md").write_text(
        f"---\nname: agentplatform-plugin-dev\ndescription: AgentPlatform 插件开发与共享能力指南\n---\n\n{formatted_content}",
        encoding="utf-8",
    )

    print("✅ 插件工程 AI 规范与平台协议已全部同步就绪！")
    print(f"  - 平台地址: {target}")
    print(f"  - 已更新: {root / 'AGENTS.md'}")
    print(f"  - 已更新: {root / 'CLAUDE.md'}")
    print(f"  - 已更新: {root / '.cursorrules'}")
    print(f"  - 已更新: {agents_skill_dir / 'SKILL.md'}")
    print("  - 已生效: 【平台共享能力复用】、【22 种富交互控件】与【双模式人肉测试协议】")
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    print("远程日志: 对接平台 /chat/sessions(待平台接入); 本地 dev 会话请见 dev 输出。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentplatform", description="AgentPlatform 插件开发 CLI 工具链")
    sub = p.add_subparsers(dest="command", required=True)

    # 1. 初始化
    sp = sub.add_parser("init", help="快速生成带共享能力示例与 AI 规范的插件脚手架")
    sp.add_argument("name", help="插件助手名称 (如 my-assistant)")
    sp.set_defaults(func=cmd_init)

    # 2. 共享能力与控件查询
    sp = sub.add_parser("registry", help="查阅平台共享公共技能 (Skill) 与工具 (Tool) 注册表")
    sp.add_argument("--target", default=None, help="远程平台服务器地址 (默认: AGENTPLATFORM_TARGET 或 http://localhost:8000)")
    sp.add_argument("--json", action="store_true", help="以 JSON 格式输出完整 Schema")
    sp.set_defaults(func=cmd_registry)

    sp = sub.add_parser("widgets", help="查阅平台支持的 22 种富交互 ContentBlock 控件清单与样例")
    sp.add_argument(
        "--category",
        choices=["display", "interactive", "action"],
        default=None,
        help="按分类过滤 (display / interactive / action)",
    )
    sp.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    sp.set_defaults(func=cmd_widgets)

    sp = sub.add_parser("guide", help="打印完整的 AgentPlatform 开发者与 AI 协同开发指南")
    sp.set_defaults(func=cmd_guide)

    # 3. 规范同步
    sp = sub.add_parser("update", help="一键从远程平台服务同步升级规范与 SDK (默认跨机器远程同步)")
    sp.add_argument("path", default=".", nargs="?")
    sp.add_argument("--no-package", action="store_true", help="仅更新规范文件，不下载安装远程 Python 包")
    sp.add_argument("--target", default=None, help="远程平台服务器地址 (默认: AGENTPLATFORM_TARGET 或 http://localhost:8000)")
    sp.set_defaults(func=cmd_update)

    # 4. 校验、测试、调试、对话、部署
    sp = sub.add_parser("validate", help="静态校验插件清单/依赖/命名空间与 Python 语法")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("test", help="执行 test/*.yaml 自动化用例")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_test)

    sp = sub.add_parser("dev", help="启动本地交互式终端对话调试 (REPL)")
    sp.add_argument("path", default=".", nargs="?")
    sp.set_defaults(func=cmd_dev)

    sp = sub.add_parser("chat", help="执行单句/多轮本地对话 (人肉测试模式后台静默调用)")
    sp.add_argument("message", nargs="?", default="", help="用户输入消息")
    sp.add_argument("--path", default=".", help="插件工程目录")
    sp.add_argument("--reset", action="store_true", help="重置当前本地多轮会话历史")
    sp.set_defaults(func=cmd_chat)

    sp = sub.add_parser("deploy", help="一键将插件部署到平台服务器")
    sp.add_argument("path", default=".", nargs="?")
    sp.add_argument("--target", default=None, help="平台服务器地址 (默认: AGENTPLATFORM_TARGET 或 http://localhost:8000)")
    sp.set_defaults(func=cmd_deploy)

    sp = sub.add_parser("logs", help="查看插件运行时日志")
    sp.set_defaults(func=cmd_logs)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
