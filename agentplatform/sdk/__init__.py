"""AgentPlatform SDK (设计 006 §5)。

提供 @skill / @tool 装饰器、Skill / Tool 基类与 Context 上下文。
"""

from agentplatform.sdk.base import (
    Context,
    Skill,
    Tool,
    get_base_url,
    get_plugin_data_dir,
)
from agentplatform.sdk.decorators import (
    as_skill_callable,
    as_tool_callable,
    skill,
    tool,
)
from agentplatform.sdk.testing import TestContext, create_test_context, render_skill

__all__ = [
    "Context",
    "Skill",
    "TestContext",
    "Tool",
    "as_skill_callable",
    "as_tool_callable",
    "create_test_context",
    "get_base_url",
    "get_plugin_data_dir",
    "render_skill",
    "skill",
    "tool",
]

