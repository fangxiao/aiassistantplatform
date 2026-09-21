"""用户自定义 LLM 端点与模型目录(用户自定义大模型,OpenAI 格式)。

- /api/llm/endpoints:当前用户的个人端点 CRUD(密钥仅本人加密存储)
- /api/llm/models:统一模型目录 = 个人端点模型 + 平台共享端点模型 +
  环境默认模型,供助手/会话选模型
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.dependencies import get_current_user
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

router = APIRouter(prefix="/llm", tags=["llm"])


class ModelOut(dict):
    pass


@router.get("/endpoints", response_model=list[LlmEndpointOut])
async def my_endpoints(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[LlmEndpoint]:
    """我的自定义端点(OpenAI 兼容;密钥不回显)。"""
    return await list_endpoints(session, owner_id=str(user.id))


@router.post("/endpoints", response_model=LlmEndpointOut, status_code=201)
async def add_my_endpoint(
    payload: LlmEndpointCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LlmEndpoint:
    """添加我的端点;设默认时仅抢占我自己的默认(不影响平台共享默认)。"""
    endpoint = await create_endpoint(session, **payload.model_dump(), owner_id=str(user.id))
    await session.commit()
    return endpoint


@router.patch("/endpoints/{endpoint_id}", response_model=LlmEndpointOut)
async def patch_my_endpoint(
    endpoint_id: uuid.UUID,
    payload: LlmEndpointUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LlmEndpoint:
    ep = await session.get(LlmEndpoint, endpoint_id)
    if ep is None or ep.owner_id != str(user.id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "端点不存在"})
    endpoint = await update_endpoint(session, endpoint_id, **payload.model_dump(exclude_unset=True))
    if endpoint is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "端点不存在"})
    await session.commit()
    return endpoint


@router.delete("/endpoints/{endpoint_id}", status_code=204)
async def delete_my_endpoint(
    endpoint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    ep = await session.get(LlmEndpoint, endpoint_id)
    if ep is None or ep.owner_id != str(user.id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "端点不存在"})
    await session.delete(ep)
    await session.commit()


@router.get("/models")
async def model_catalog(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """统一模型目录:个人 + 平台共享 + 环境默认,去重。"""
    mine = await list_endpoints(session, owner_id=str(user.id))
    shared = await list_endpoints(session)
    seen: set[str] = set()
    models: list[dict] = []

    def add(model: str, source: str, endpoint_id=None, is_default: bool = False):
        if model and model not in seen:
            seen.add(model)
            models.append({"model": model, "source": source, "endpoint_id": endpoint_id, "is_default": is_default})

    for ep in mine:
        add(ep.model, "personal", str(ep.id), ep.is_default)
    for ep in shared:
        add(ep.model, "platform", str(ep.id), ep.is_default)
    if settings.default_model:
        add(settings.default_model, "env_default", None, True)
    return {"models": models}
