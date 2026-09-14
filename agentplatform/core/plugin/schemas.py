"""插件 API 响应模型(设计 005 §5)。

description/model 取自 manifest 摘要;完整清单见插件详情(部署响应不回全文)。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from agentplatform.core.plugin.manifest import infer_display_name
from agentplatform.core.plugin.model import Plugin, PluginStatus


class PluginOut(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str | None = None
    version: str
    status: PluginStatus
    description: str | None = None
    model: str | None = None
    mounted_kb_ids: list[uuid.UUID] = []
    deployed_at: datetime


def to_out(plugin: Plugin) -> PluginOut:
    """ORM -> 响应模型(description/model/display_name 从 manifest 摘出)。"""
    m = plugin.manifest or {}
    display_name = m.get("display_name") or m.get("title") or infer_display_name(m.get("description"), plugin.name)
    return PluginOut(
        id=plugin.id,
        name=plugin.name,
        display_name=display_name,
        version=plugin.version,
        status=plugin.status,
        description=m.get("description"),
        model=m.get("model"),
        mounted_kb_ids=[uuid.UUID(k) for k in (plugin.mounted_kb_ids or [])],
        deployed_at=plugin.deployed_at,
    )
