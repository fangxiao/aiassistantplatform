"""注册表资源 -> OpenAI tools 参数(设计 002 §5.1 显式调用协议)。

把插件依赖的 skill/tool 映射为 OpenAI function 定义,LLM 通过 tool_calls 显式发起。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.model import SkillTool, SkillToolKind
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


def _sanitize_schema(schema: dict) -> dict:
    """递归确保 schema 中所有 properties / items 的 description 均为非空字符串，避免网关 Pydantic 校验失败。"""
    if not isinstance(schema, dict):
        return schema
    res = {}
    for k, v in schema.items():
        if k == "properties" and isinstance(v, dict):
            new_props = {}
            for pk, pv in v.items():
                if isinstance(pv, dict):
                    sanitized_pv = _sanitize_schema(pv)
                    if not sanitized_pv.get("description"):
                        sanitized_pv["description"] = f"{pk} 字段"
                    new_props[pk] = sanitized_pv
                else:
                    new_props[pk] = pv
            res[k] = new_props
        elif k == "items" and isinstance(v, dict):
            res[k] = _sanitize_schema(v)
        else:
            res[k] = _sanitize_schema(v) if isinstance(v, dict) else v
    return res


def to_function_schema(row: SkillTool) -> dict:
    """注册表行 -> OpenAI function 定义。"""
    schema = row.schema_ or {}
    if "properties" in schema or schema.get("type") == "object":
        params = schema
    else:
        params = schema.get("parameters") or {"type": "object", "properties": {}}
    params = _sanitize_schema(params)
    desc = row.description or f"Skill or Tool: {row.name or row.id}"
    safe_name = row.id.replace(":", "__")
    return {
        "type": "function",
        "function": {
            "name": safe_name,
            "description": desc,
            "parameters": params,
        },
    }


async def build_tools(
    session: AsyncSession, resource_ids: list[str], include_output_block: bool = True
) -> list[dict]:
    """把资源 id 列表解析为 OpenAI tools(002 §5.1);缺失的资源跳过。

    kb: 资源(kind=kb)不是可调用函数,不下发(检索经 tool:kb_search,设计 008 §4.1)。
    """
    tools: list[dict] = []
    if include_output_block:
        tools.append(OUTPUT_BLOCK_TOOL)
    for rid in resource_ids:
        row = await resolve(session, rid)
        if row is not None and row.kind != SkillToolKind.kb:
            tools.append(to_function_schema(row))
    return tools

