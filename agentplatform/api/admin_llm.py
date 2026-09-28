"""LLM 端点管理 API(设计 005 §7)。

平台级配置,仅 admin(require_admin,ADR 0008);个人模型走 /llm/my-models。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import require_admin
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.llm.schemas import (
    LlmEndpointCreate,
    LlmEndpointOut,
    LlmEndpointUpdate,
)
from agentplatform.core.llm.service import (
    create_endpoint,
    list_endpoints,
    update_endpoint,
)

router = APIRouter(prefix="/admin/llm-endpoints", tags=["admin"])


@router.get("", response_model=list[LlmEndpointOut])
async def get_endpoints(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> list[LlmEndpoint]:
    """平台共享端点列表(仅 admin);response_model 负责脱敏序列化。"""
    return await list_endpoints(session)


@router.post("", response_model=LlmEndpointOut, status_code=201)
async def post_endpoint(
    payload: LlmEndpointCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> LlmEndpoint:
    """新增平台共享端点(仅 admin);api_key 加密存储。"""
    endpoint = await create_endpoint(session, **payload.model_dump())
    await session.commit()
    return endpoint


@router.patch("/{endpoint_id}", response_model=LlmEndpointOut)
async def patch_endpoint(
    endpoint_id: uuid.UUID,
    payload: LlmEndpointUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> LlmEndpoint:
    """更新端点(部分字段,仅 admin);is_default=true 会抢占默认。"""
    endpoint = await update_endpoint(
        session, endpoint_id, **payload.model_dump(exclude_unset=True)
    )
    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"端点不存在: {endpoint_id}"},
        )
    await session.commit()
    return endpoint
