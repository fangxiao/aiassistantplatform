"""skill:cross_document_compare —— 多文档/多实体横向比对技能(平台内置)。

RFC-2026-001 §RFC-4:多源数据横向比对矩阵抽取。
输入多个实体(每个含 name + content)与对比维度,输出 comparison_matrix 与
summary_markdown。通用能力:适用于竞品研报、合同比对、多候选人评估等场景。
"""

import json

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "skill:cross_document_compare",
    "kind": "skill",
    "name": "cross_document_compare",
    "version": "1.0.0",
    "description": "多文档/多实体横向比对,输出对比矩阵与摘要",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "description": "对比实体列表,每项含 name 与 content",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "实体名称"},
                            "content": {"type": "string", "description": "实体内容"},
                        },
                        "required": ["name", "content"],
                    },
                },
                "dimensions": {
                    "type": "array",
                    "description": "对比维度列表,如 功能覆盖/价格模式/优劣势",
                    "items": {"type": "string"},
                },
            },
            "required": ["entities", "dimensions"],
        },
        "returns": {
            "type": "object",
            "description": "comparison_matrix 与 summary_markdown",
        },
    },
}

PROMPT_TEMPLATE = """你是一个多源文档横向对比分析专家。请对以下多个实体按指定维度进行横向对比。

【对比实体】
{entities}

【对比维度】
{dimensions}

请严格按以下 JSON 结构输出(不要输出其他内容):
{{
  "comparison_matrix": [
    {{"dimension": "维度名", "rows": [{{"entity": "实体名", "value": "该维度下的表现/内容"}}]}}
  ],
  "summary_markdown": "一段用 Markdown 表格呈现的横向对比总结,含表头(维度/实体1/实体2/...)与各行数据"
}}

要求:
1. comparison_matrix 的 dimensions 字段必须覆盖给定的全部维度
2. 每个维度下必须包含所有实体
3. value 要基于实体内容客观提炼,不得臆造
4. summary_markdown 用 Markdown 表格横向对比所有实体,并给出 2-3 句核心结论

输出:"""


def build_prompt(entities: list[dict], dimensions: list[str]) -> str:
    """按参数填充 prompt 模板(simple skill 的执行入口)。"""
    entities_text = "\n".join(
        f"[{e.get('name', '')}]\n{e.get('content', '')}" for e in entities
    )
    dimensions_text = "\n".join(f"- {d}" for d in dimensions)
    return PROMPT_TEMPLATE.format(entities=entities_text, dimensions=dimensions_text)
