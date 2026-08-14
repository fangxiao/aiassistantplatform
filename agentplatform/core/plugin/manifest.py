"""插件清单模型(设计 006 §2 plugin.yaml / 002 §4)。

M4 以结构化 JSON 接收清单(YAML 解析在 M9 CLI 引入 PyYAML 后负责);
字段与 006 plugin.yaml 对齐。
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResourceDef(BaseModel):
    """插件自有 skill/tool 定义。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    file: str
    description: str | None = None
    schema_: dict | None = Field(default=None, alias="schema")  # JSON 键为 schema


class PluginManifest(BaseModel):
    """插件清单(对应 plugin.yaml)。"""

    name: str
    version: str
    description: str | None = None
    author: str | None = None
    model: str | None = None
    depends_on: list[str] = []
    skills: list[ResourceDef] = []
    tools: list[ResourceDef] = []

    @field_validator("skills", "tools")
    @classmethod
    def _no_duplicate_ids(cls, v: list[ResourceDef]) -> list[ResourceDef]:
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("skill/tool id 重复")
        return v
