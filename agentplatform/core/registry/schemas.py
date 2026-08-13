"""注册表 API 响应模型(设计 002 §3.2 资源元信息)。"""

from pydantic import BaseModel, ConfigDict, Field

from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource


class SkillToolOut(BaseModel):
    """单条资源元信息;schema 为 OpenAI function 兼容的输入输出 schema。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    kind: SkillToolKind
    name: str
    version: str
    source: SkillToolSource
    description: str | None = None
    schema_: dict = Field(alias="schema")  # JSON 键为 schema,避免遮蔽 BaseModel 属性


def to_out(row: SkillTool) -> SkillToolOut:
    """ORM -> 响应模型(ORM 属性 schema_ 映射到响应字段 schema)。"""
    return SkillToolOut(
        id=row.id,
        kind=row.kind,
        name=row.name,
        version=row.version,
        source=row.source,
        description=row.description,
        schema=row.schema_,
    )
