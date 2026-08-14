"""skill:structured_output —— 结构化输出 skill(平台内置)。

简单 skill:按给定 JSON Schema 约束模型输出结构化结果,
用于把自由文本转换为可机读 JSON。
"""

import json

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "skill:structured_output",
    "kind": "skill",
    "name": "structured_output",
    "version": "1.0.0",
    "description": "让模型按给定 JSON Schema 输出结构化结果",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {"type": "string", "description": "任务说明"},
                "json_schema": {"type": "object", "description": "目标 JSON Schema"},
                "content": {"type": "string", "description": "待处理的输入内容"},
            },
            "required": ["instruction", "json_schema", "content"],
        },
        "returns": {"type": "object", "description": "按 schema 的结构化 JSON"},
    },
}

PROMPT_TEMPLATE = """任务:{instruction}

请只输出符合以下 JSON Schema 的合法 JSON,不要输出任何其他内容:
{schema}

输入内容:
{content}

输出:"""


def build_prompt(instruction: str, json_schema: dict, content: str) -> str:
    """按参数填充 prompt 模板(simple skill 的执行入口)。"""
    schema_text = json.dumps(json_schema, ensure_ascii=False, indent=2)
    return PROMPT_TEMPLATE.format(
        instruction=instruction, schema=schema_text, content=content
    )
