"""上下文组装(设计 001 §core/agent / 002 §5 显式调用)。

系统提示告知可显式调用的 skill/tool;消息序列为 [system, ...history, user]。
Redis 会话缓存留 M6(sessions/messages)。
"""

from agentplatform.core.registry.model import SkillTool


def build_system_prompt(
    resources: list[SkillTool], plugin_desc: str | None = None
) -> str:
    """系统提示:说明可显式调用的 skill/tool(002 §5.1 显式调用引导)。"""
    lines: list[str] = []
    if plugin_desc:
        lines.append(f"当前助手: {plugin_desc}")
    lines.append(
        "你是 agentplatform 的 AI 助手,可通过 function calling 显式调用以下 skill/tool:"
    )
    for r in resources:
        lines.append(f"- {r.id}: {r.description or ''}")
    lines.append("需要时主动调用,不要编造调用结果。")
    return "\n".join(lines)


def build_messages(
    system_prompt: str | None, history: list[dict] | None, user_message: str
) -> list[dict]:
    """组装 [system, ...history, user];history 为 {role, content} 列表。"""
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_message})
    return messages
