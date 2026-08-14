"""插件 API 响应模型(设计 005 §5)。

description/model 取自 manifest 摘要;完整清单见插件详情(部署响应不回全文)。
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from agentplatform.core.plugin.model import Plugin, PluginStatus


class PluginOut(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    status: PluginStatus
    description: str | None = None
    model: str | None = None
    deployed_at: datetime


def to_out(plugin: Plugin) -> PluginOut:
    """ORM -> 响应模型(description/model 从 manifest 摘出)。"""
    m = plugin.manifest or {}
    return PluginOut(
        id=plugin.id,
        name=plugin.name,
        version=plugin.version,
        status=plugin.status,
        description=m.get("description"),
        model=m.get("model"),
        deployed_at=plugin.deployed_at,
    )
