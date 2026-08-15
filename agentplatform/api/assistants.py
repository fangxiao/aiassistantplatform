"""助手广场 API(设计 005 §3 / M8.2)。

Plugin 即 Assistant:查询已激活的插件供用户浏览、选用与创建对话。
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import (
    get_current_user,
    get_optional_current_user,
)
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.plugin.model import Plugin, PluginStatus

router = APIRouter(prefix="/assistants", tags=["assistants"])


class AssistantOut(BaseModel):
    """助手市场输出模型。"""

    id: uuid.UUID
    name: str
    version: str
    description: str | None = None
    author: str | None = None
    model: str | None = None
    depends_on: list[str] = []
    deployed_at: datetime
    manifest: dict[str, Any]


def _plugin_to_assistant(p: Plugin) -> AssistantOut:
    manifest = p.manifest if isinstance(p.manifest, dict) else {}
    return AssistantOut(
        id=p.id,
        name=p.name,
        version=p.version,
        description=manifest.get("description"),
        author=manifest.get("author"),
        model=manifest.get("model"),
        depends_on=manifest.get("depends_on", []),
        deployed_at=p.deployed_at,
        manifest=manifest,
    )


@router.get("", response_model=list[AssistantOut])
async def list_assistants(
    query: str | None = Query(default=None, description="搜索关键词"),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_current_user),
) -> list[AssistantOut]:
    """获取可用助手列表(仅展示 active 状态插件)。"""
    stmt = (
        select(Plugin)
        .where(Plugin.status == PluginStatus.active)
        .order_by(Plugin.deployed_at.desc())
    )
    rows = await session.scalars(stmt)
    results = [_plugin_to_assistant(p) for p in rows]
    if query:
        q = query.lower()
        results = [
            a
            for a in results
            if q in a.name.lower() or (a.description and q in a.description.lower())
        ]
    return results


@router.get("/{assistant_id}", response_model=AssistantOut)
async def get_assistant_detail(
    assistant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_current_user),
) -> AssistantOut:

    """获取单个助手详情。"""
    plugin = await session.get(Plugin, assistant_id)
    if plugin is None or plugin.status != PluginStatus.active:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"助手不存在或未启用: {assistant_id}"},
        )
    return _plugin_to_assistant(plugin)
