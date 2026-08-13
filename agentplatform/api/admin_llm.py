"""LLM 端点管理 API(设计 005 §7)。

MVP 不做细粒度鉴权(M1 认证后接入);端点属于平台管理面。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

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
) -> list[LlmEndpoint]:
    """端点列表(不含明文 api_key);response_model 负责脱敏序列化。"""
    return await list_endpoints(session)


@router.post("", response_model=LlmEndpointOut, status_code=201)
async def post_endpoint(
    payload: LlmEndpointCreate,
    session: AsyncSession = Depends(get_session),
) -> LlmEndpoint:
    """新增端点;api_key 加密存储。"""
    return await create_endpoint(session, **payload.model_dump())


@router.patch("/{endpoint_id}", response_model=LlmEndpointOut)
async def patch_endpoint(
    endpoint_id: uuid.UUID,
    payload: LlmEndpointUpdate,
    session: AsyncSession = Depends(get_session),
) -> LlmEndpoint:
    """更新端点(部分字段);is_default=true 会抢占默认。"""
    endpoint = await update_endpoint(
        session, endpoint_id, **payload.model_dump(exclude_unset=True)
    )
    if endpoint is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"端点不存在: {endpoint_id}"},
        )
    return endpoint
