"""AgentPlatform SDK 单元测试辅助模块 (agentplatform.sdk.testing)。

供插件开发者在 pytest 单元测试中模拟 Context、测试 Skill 渲染与 Tool 执行。
"""

from __future__ import annotations

from typing import Any

from agentplatform.sdk.base import Context, Skill, Tool


class TestContext(Context):
    """测试专用的运行时上下文，提供状态记录与辅助断言。"""

    __test__ = False  # 避免 pytest 将其误识别为测试用例类

    def __init__(

        self,
        session_id: str = "test-session-id",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(session_id=session_id, extra=extra or {})
        self.emitted_blocks: list[dict[str, Any]] = []

    def record_block(self, block: dict[str, Any]) -> None:
        """记录 output_block 产生的组件。"""
        self.emitted_blocks.append(block)


def create_test_context(
    session_id: str = "test-session-id",
    **extra: Any,
) -> TestContext:
    """快速创建测试上下文工厂函数。"""
    return TestContext(session_id=session_id, extra=extra)


def render_skill(
    skill_cls: type[Skill],
    args: dict[str, Any],
    ctx: Context | None = None,
) -> str:
    """便捷测试 Skill 类的 Prompt 渲染结果。"""
    instance = skill_cls(ctx=ctx or create_test_context())
    return instance.execute(instance.ctx, args)
