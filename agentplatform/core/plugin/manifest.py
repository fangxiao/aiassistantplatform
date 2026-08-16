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
    code: str | None = None  # 源码内容 (支持跨机器/分布式部署时服务端持久化存储与加载)
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


def validate_manifest(manifest: PluginManifest) -> None:
    """结构校验;不通过抛 PluginValidationError(无 DB 依赖)。"""
    from agentplatform.core.plugin.errors import PluginValidationError
    from agentplatform.core.registry.version import parse

    if not manifest.name.strip():
        raise PluginValidationError("name 不能为空")
    try:
        parse(manifest.version)
    except ValueError as exc:
        raise PluginValidationError(f"version 非法: {exc}") from exc
    for r in manifest.skills:
        if not r.id.startswith("skill:"):
            raise PluginValidationError(f"skill id 必须以 'skill:' 开头: {r.id}")
    for r in manifest.tools:
        if not r.id.startswith("tool:"):
            raise PluginValidationError(f"tool id 必须以 'tool:' 开头: {r.id}")

