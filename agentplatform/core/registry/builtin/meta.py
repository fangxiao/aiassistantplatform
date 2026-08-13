"""内置资源元信息类型(设计 002 §3.2)。"""

from typing import TypedDict


class ResourceMeta(TypedDict):
    """内置资源自描述元信息,与 skill_tools 表字段对应。"""

    id: str
    kind: str
    name: str
    version: str
    description: str
    schema: dict
