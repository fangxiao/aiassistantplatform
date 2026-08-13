"""skill:summarize —— 摘要 skill(平台内置)。

简单 skill(设计 002 §5.3):prompt 模板 + 参数,执行时填充参数交给模型,
由主 agent 的 LLM 调用完成(不引入子 agent)。
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "skill:summarize",
    "kind": "skill",
    "name": "summarize",
    "version": "1.0.0",
    "description": "按指定风格与长度摘要文本",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "待摘要文本"},
                "style": {
                    "type": "string",
                    "enum": ["concise", "detailed"],
                    "description": "摘要风格",
                },
                "max_words": {
                    "type": "integer",
                    "description": "摘要最大字数",
                },
            },
            "required": ["text"],
        },
        "returns": {"type": "string", "description": "摘要结果"},
    },
}

PROMPT_TEMPLATE = """请对下面的文本进行摘要,风格:{style},不超过 {max_words} 字。

文本:
{text}

摘要:"""


def build_prompt(text: str, style: str = "concise", max_words: int = 200) -> str:
    """按参数填充 prompt 模板(simple skill 的执行入口)。"""
    return PROMPT_TEMPLATE.format(text=text, style=style, max_words=max_words)
