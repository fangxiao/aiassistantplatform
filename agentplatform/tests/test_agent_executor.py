"""tool/skill 执行器测试:实现解析、确定性 tool、简单 skill(prompt 模板 + LLM 调用)。"""

import pytest

from agentplatform.core.agent.errors import AgentExecError
from agentplatform.core.agent.executor import execute_skill, execute_tool, resolve_impl
from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource

FIXTURE_TOOL = "agentplatform.tests.fixtures.impl_tool"
BUILTIN_SUMMARIZE = "agentplatform.core.registry.builtin.summarize"


def _row(resource_id: str, impl_path: str) -> SkillTool:
    return SkillTool(
        id=resource_id,
        version="1.0.0",
        kind=SkillToolKind.tool if resource_id.startswith("tool:") else SkillToolKind.skill,
        name=resource_id.split(":", 1)[1],
        source=SkillToolSource.builtin,
        schema_={},
        impl_path=impl_path,
    )


class TestResolveImpl:
    def test_builtin_importable(self) -> None:
        assert resolve_impl(_row("skill:summarize", BUILTIN_SUMMARIZE)) is not None

    def test_missing_path_raises(self) -> None:
        with pytest.raises(AgentExecError, match="impl_path"):
            resolve_impl(_row("tool:x", ""))

    def test_plugin_code_not_loaded_raises(self) -> None:
        with pytest.raises(AgentExecError, match="M9"):
            resolve_impl(_row("skill:prd_review", "./skills/prd_review.py"))


class TestExecuteTool:
    async def test_deterministic_tool(self) -> None:
        result = await execute_tool(_row("tool:echo", FIXTURE_TOOL), {"text": "hi"})
        assert result == "HI"

    async def test_missing_run_raises(self) -> None:
        with pytest.raises(AgentExecError, match="run"):
            await execute_tool(_row("tool:summarize", BUILTIN_SUMMARIZE), {})  # skill 模块无 run


class TestExecuteSkill:
    async def test_prompt_template_then_llm_call(self) -> None:
        captured: dict = {}

        async def fake_llm(prompt: str) -> str:
            captured["prompt"] = prompt
            return "摘要结果"

        result = await execute_skill(
            _row("skill:summarize", BUILTIN_SUMMARIZE),
            {"text": "很长的一段文字", "style": "concise", "max_words": 50},
            fake_llm,
        )
        assert result == "摘要结果"
        assert "很长的一段文字" in captured["prompt"]
        assert "concise" in captured["prompt"]
