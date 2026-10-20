"""测试用异步 tool:覆盖 __tool_registry__ 注册表路径(savetoken 工单回归)。"""

from agentplatform.sdk.decorators import tool


@tool(id="tool:async_echo", version="1.0.0", description="异步回声")
async def async_echo(text: str) -> str:
    return f"echo:{text}"
