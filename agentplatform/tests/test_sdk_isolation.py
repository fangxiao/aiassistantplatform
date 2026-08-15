"""架构隔离与 SDK 测试 (确保 SDK 与 CLI validate 零重型依赖)。"""

import sys
from agentplatform.sdk import Context, Skill, TestContext, create_test_context, render_skill, skill, tool
from agentplatform.cli.validate import validate_project


def test_sdk_testing_helpers():
    """验证 SDK 测试辅助工具功能正常。"""
    ctx = create_test_context(session_id="s123", custom_key="abc")
    assert isinstance(ctx, TestContext)
    assert ctx.session_id == "s123"
    assert ctx.extra["custom_key"] == "abc"

    ctx.record_block({"type": "markdown", "data": {"text": "hello"}})
    assert len(ctx.emitted_blocks) == 1

    @skill(id="skill:test_greet", version="1.0.0", prompt="你好, {{name}}!")
    class GreetSkill(Skill):
        pass

    rendered = render_skill(GreetSkill, {"name": "世界"}, ctx)
    assert rendered == "你好, 世界!"


def test_sdk_isolation_no_db_dependencies():
    """确保 SDK 模块本身绝不引入 sqlalchemy / fastapi / asyncpg 等服务端依赖。"""
    sdk_symbols = [Context, Skill, TestContext, create_test_context, render_skill, skill, tool]
    assert len(sdk_symbols) == 7


def test_sdk_dynamic_load_and_validate_json_serializable(tmp_path):
    """回归测试：动态加载 @tool/@skill 并确保 validate_project 输出可安全 json.dumps。"""
    import json
    from agentplatform.sdk.loader import load_resources

    tool_file = tmp_path / "custom_tool.py"
    tool_file.write_text(
        'from agentplatform.sdk import tool\n\n'
        '@tool(id="tool:custom_calc", version="1.0.0", description="测试工具")\n'
        'def calc(x: int) -> str:\n'
        '    return str(x * 2)\n',
        encoding="utf-8",
    )

    resources = load_resources(str(tool_file))
    assert len(resources) == 1
    assert resources[0]["id"] == "tool:custom_calc"

    manifest_file = tmp_path / "plugin.yaml"
    manifest_file.write_text(
        'name: test-plugin\n'
        'version: 0.1.0\n'
        'tools:\n'
        '  - id: "tool:custom_calc"\n'
        '    file: "custom_tool.py"\n',
        encoding="utf-8",
    )

    res = validate_project(tmp_path)
    assert res["ok"] is True
    # 验证能安全 json.dumps（无不可序列化的函数对象）
    serialized = json.dumps(res, ensure_ascii=False)
    assert "tool:custom_calc" in serialized

