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



def rewrite_html_img_proxy(html: str) -> str:
    """把 HTML 中全部外链 <img src> 改写为平台代理签名 URL(T18 项8)。

    插件写盘前一行调用即可;幂等,已代理/平台自身文件 URL 保持原样。
    2026-09-26 增强改写为"验活"版:上游死链(404/过期/编造)自动替换为
    占位图,警告以 HTML 注释(embedded)随产物携带,供 checkup 提取。
    """
    from agentplatform.core.agent.img_proxy import rewrite_html_checked

    out, warnings = rewrite_html_checked(html)
    if warnings:
        out += "\n<!-- imgproxy-warnings: " + " | ".join(warnings) + " -->"
    return out
