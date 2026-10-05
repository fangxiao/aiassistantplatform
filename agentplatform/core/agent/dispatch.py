"""工具调用解析与资源匹配(设计 016 §3 / M21 P2.4,自 loop.py 迁出)。

文本兜底解析(截断启发式)对模型输出格式敏感——集中于此便于 H5 按端点
能力分流与可观测收敛。
"""

import json

from agentplatform.core.agent.errors import AgentExecError  # noqa: F401
from agentplatform.core.registry.model import SkillTool


def _find_resource(name: str, resources: dict[str, SkillTool]) -> SkillTool | None:
    """鲁棒解析工具/技能资源，兼容带前缀、下划线转换、点号路径、版本号后缀等全部变体。"""
    if not name:
        return None
    if name in resources:
        return resources[name]
    norm = name.replace("__", ":")
    if norm in resources:
        return resources[norm]
    bare = norm.split(":", 1)[-1].split("@", 1)[0].strip()
    if bare in resources:
        return resources[bare]
    if name.startswith("tool_"):
        candidate = f"tool:{name[5:]}"
        if candidate in resources:
            return resources[candidate]
    if name.startswith("skill_"):
        candidate = f"skill:{name[6:]}"
        if candidate in resources:
            return resources[candidate]
    dot_replaced = bare.replace(".", "_")
    if dot_replaced in resources:
        return resources[dot_replaced]
    for k, v in resources.items():
        if (
            k == bare
            or v.name == bare
            or v.name == dot_replaced
            or k.endswith((f":{bare}", f"__{bare}"))
            or bare == k.split(":", 1)[-1]
            or (v.impl_path and v.impl_path.endswith(bare))
            or (v.impl_path and v.impl_path.replace(".", "_").endswith(dot_replaced))
        ):
            return v
    return None

def _parse_args(arguments: str) -> dict:
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}


# M26 瘦身(设计 016 §3 ≤400 行目标):文本兜底解析迁出至 text_fallback;
# 此处转出口保既有导入路径(loop 等)
from agentplatform.core.agent.text_fallback import (  # noqa: F401
    _extract_text_tool_calls,
    _strip_tool_syntax,
)
