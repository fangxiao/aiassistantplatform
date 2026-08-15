"""平台端“外部开发者黑盒集成测试” (Black-box E2E Dogfooding Test)。

模拟外部开发者在无平台源码权限的完全隔离临时目录中：
1. agentplatform init 创建脚手架
2. 检验生成的 AGENTS.md / CLAUDE.md 边界协议
3. 编写符合规范的 @skill / @tool 与测试
4. 执行 validate / test 流水线
5. 验证异常诊断与自愈能力（错误不穿透、不泄露 Traceback）
"""

import argparse
import json
from pathlib import Path

import pytest

from agentplatform.cli.main import cmd_init, cmd_test, cmd_validate

from agentplatform.cli.validate import validate_project


def test_blackbox_plugin_developer_lifecycle_success(tmp_path: Path):
    """测试标准开发者从 init 到 validate、test 的完整成功闭环。"""
    plugin_dir = tmp_path / "search_assistant"

    # 1. 模拟外部开发者执行 agentplatform init
    args = argparse.Namespace(name=str(plugin_dir))
    code = cmd_init(args)
    assert code == 0
    assert (plugin_dir / "plugin.yaml").exists()
    assert (plugin_dir / "AGENTS.md").exists()
    assert (plugin_dir / "CLAUDE.md").exists()

    # 2. 验证脚手架生成的协议中包含系统边界隔离红线
    agents_md = (plugin_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "CRITICAL BOUNDARIES" in agents_md
    assert "严禁" in agents_md

    # 3. 模拟开发者编写自定义工具与技能
    custom_tool = plugin_dir / "tools" / "search.py"
    custom_tool.write_text(
        'from agentplatform.sdk import tool\n\n'
        '@tool(\n'
        '    id="tool:web_search",\n'
        '    version="1.0.0",\n'
        '    description="搜索网络内容",\n'
        '    schema={\n'
        '        "type": "object",\n'
        '        "properties": {"query": {"type": "string"}},\n'
        '        "required": ["query"],\n'
        '    },\n'
        ')\n'
        'def search(query: str = "") -> str:\n'
        '    return f"Result for {query}"\n',
        encoding="utf-8",
    )

    custom_skill = plugin_dir / "skills" / "answer.py"
    custom_skill.write_text(
        'from agentplatform.sdk import Skill, skill, Context\n\n'
        '@skill(\n'
        '    id="skill:smart_answer",\n'
        '    version="1.0.0",\n'
        '    description="智能问答技能",\n'
        '    schema={"type": "object", "properties": {"question": {"type": "string"}}},\n'
        '    prompt="请回答: {{question}}",\n'
        ')\n'
        'class SmartAnswer(Skill):\n'
        '    pass\n',
        encoding="utf-8",
    )

    # 4. 更新 plugin.yaml 清单声明
    manifest_path = plugin_dir / "plugin.yaml"
    manifest_path.write_text(
        'name: search_assistant\n'
        'version: 0.1.0\n'
        'description: 智能搜索插件\n'
        'depends_on: ["tool:pdf_parse@^1.0"]\n'
        'tools:\n'
        '  - id: "tool:web_search"\n'
        '    file: "tools/search.py"\n'
        'skills:\n'
        '  - id: "skill:smart_answer"\n'
        '    file: "skills/answer.py"\n',
        encoding="utf-8",
    )

    # 5. 执行静态校验
    val_res = validate_project(plugin_dir)
    assert val_res["ok"] is True
    assert len(val_res["errors"]) == 0
    assert len(val_res["resources"]) == 2

    # 验证序列化绝对安全
    serialized = json.dumps(val_res, ensure_ascii=False)
    assert "tool:web_search" in serialized
    assert "skill:smart_answer" in serialized

    # 6. 验证 CLI 命令返回值
    val_args = argparse.Namespace(path=str(plugin_dir))
    assert cmd_validate(val_args) == 0


def test_blackbox_plugin_developer_error_diagnostics(tmp_path: Path):
    """测试各种开发者错误场景下，CLI 返回友好结构化诊断且绝不崩溃抛栈。"""
    plugin_dir = tmp_path / "broken_plugin"
    plugin_dir.mkdir(parents=True)

    # 场景 1：缺少 plugin.yaml
    res = validate_project(plugin_dir)
    assert res["ok"] is False
    assert any("缺少 plugin.yaml" in e for e in res["errors"])

    # 场景 2：清单存在但声明的文件不存在
    (plugin_dir / "plugin.yaml").write_text(
        'name: broken_plugin\n'
        'version: 1.0.0\n'
        'tools:\n'
        '  - id: "tool:missing"\n'
        '    file: "tools/non_existent.py"\n',
        encoding="utf-8",
    )
    res = validate_project(plugin_dir)
    assert res["ok"] is False
    assert any("资源实现文件不存在" in e for e in res["errors"])

    # 场景 3：实现文件中未找到声明的 ID
    (plugin_dir / "tools").mkdir()
    (plugin_dir / "tools" / "empty.py").write_text(
        '# 没有任何 @tool 装饰器\n',
        encoding="utf-8",
    )
    (plugin_dir / "plugin.yaml").write_text(
        'name: broken_plugin\n'
        'version: 1.0.0\n'
        'tools:\n'
        '  - id: "tool:missing_decorator"\n'
        '    file: "tools/empty.py"\n',
        encoding="utf-8",
    )
    res = validate_project(plugin_dir)
    assert res["ok"] is False
    assert any("未找到被 @tool 装饰的资源" in e for e in res["errors"])


@pytest.mark.asyncio
async def test_blackbox_dev_mode_tool_execution(tmp_path: Path):
    """测试本地 dev 模式下，自定义插件 Tool 能够被执行器真正执行并返回结果。"""
    from agentplatform.cli.dev import _attach_dev_impls
    from agentplatform.core.agent.executor import execute_tool
    from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource

    plugin_dir = tmp_path / "calc_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "tools").mkdir()

    tool_file = plugin_dir / "tools" / "calc.py"
    tool_file.write_text(
        'from agentplatform.sdk import tool\n\n'
        '@tool(id="tool:multiply", version="1.0.0", description="乘法运算")\n'
        'def multiply(a: int, b: int) -> str:\n'
        '    return str(int(a) * int(b))\n',
        encoding="utf-8",
    )

    (plugin_dir / "plugin.yaml").write_text(
        'name: calc_plugin\n'
        'version: 1.0.0\n'
        'tools:\n'
        '  - id: "tool:multiply"\n'
        '    file: "tools/calc.py"\n',
        encoding="utf-8",
    )

    # 1. 模拟 dev 模式绑定本地实现
    _attach_dev_impls(plugin_dir)

    # 2. 模拟调度器执行工具
    dummy_resource = SkillTool(
        id="tool:multiply",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="multiply",
        source=SkillToolSource.private,
        schema_={},
        impl_path="",
    )

    result = await execute_tool(dummy_resource, {"a": 6, "b": 7})
    assert result == "42"

