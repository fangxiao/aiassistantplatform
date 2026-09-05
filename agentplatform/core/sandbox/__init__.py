"""AgentPlatform 沙箱子系统。

基于 @anthropic-ai/sandbox-runtime (srt) 封装的 OS 原语级轻量进程安全沙箱。
"""

from agentplatform.core.sandbox.policy import SandboxPolicy, generate_sandbox_policy
from agentplatform.core.sandbox.runner import (
    SandboxResult,
    execute_command_in_sandbox,
    is_high_risk_tool,
    is_sandbox_available,
)

__all__ = [
    "SandboxPolicy",
    "SandboxResult",
    "execute_command_in_sandbox",
    "generate_sandbox_policy",
    "is_high_risk_tool",
    "is_sandbox_available",
]
