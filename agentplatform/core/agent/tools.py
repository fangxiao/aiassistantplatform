"""注册表资源 -> OpenAI tools 参数(设计 002 §5.1 显式调用协议)。

把插件依赖的 skill/tool 映射为 OpenAI function 定义,LLM 通过 tool_calls 显式发起。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.model import SkillTool
from agentplatform.core.registry.service import resolve

OUTPUT_BLOCK_TOOL = {
    "type": "function",
    "function": {
        "name": "output_block",
        "description": "输出富交互组件 ContentBlock(如 card, table, input.form, input.confirm, mermaid 等)",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "ContentBlock 类型 (如 markdown, code, table, card, collapsible, input.confirm, input.form 等)",
                },
                "data": {
                    "type": "object",
                    "description": "组件数据结构",
                },
                "meta": {
                    "type": "object",
                    "description": "可选块级元信息",
                },
            },
            "required": ["type", "data"],
        },
    },
}


def to_function_schema(row: SkillTool) -> dict:
    """注册表行 -> OpenAI function 定义。"""
    params = (row.schema_ or {}).get("parameters", {"type": "object"})
    return {
        "type": "function",
        "function": {
            "name": row.id,
            "description": row.description or "",
            "parameters": params,
        },
    }


async def build_tools(
    session: AsyncSession, resource_ids: list[str], include_output_block: bool = True
) -> list[dict]:
    """把资源 id 列表解析为 OpenAI tools(002 §5.1);缺失的资源跳过。"""
    tools: list[dict] = []
    if include_output_block:
        tools.append(OUTPUT_BLOCK_TOOL)
    for rid in resource_ids:
        row = await resolve(session, rid)
        if row is not None:
            tools.append(to_function_schema(row))
    return tools

