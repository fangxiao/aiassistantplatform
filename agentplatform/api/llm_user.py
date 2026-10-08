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
    """统一模型目录:个人(含供应商分组)+ 平台共享 + 环境默认,去重。"""
    from sqlalchemy import select

    from agentplatform.core.llm.provider_model import LlmProvider

    mine = await list_endpoints(session, owner_id=str(user.id))
    shared = await list_endpoints(session)
    provider_names = {
        str(p.id): p.name
        for p in (
            await session.scalars(
                select(LlmProvider).where(LlmProvider.user_id == str(user.id))
            )
        ).all()
    }
    seen: set[str] = set()
    models: list[dict] = []

    def add(model: str, source: str, endpoint_id=None, is_default: bool = False, provider: str | None = None):
        if model and model not in seen:
            seen.add(model)
            models.append({
                "model": model, "source": source, "endpoint_id": endpoint_id,
                "is_default": is_default, "provider": provider,
            })

    for ep in mine:
        add(
            ep.model, "personal", str(ep.id), ep.is_default,
            provider=provider_names.get(str(ep.provider_id)) if ep.provider_id else None,
        )
    for ep in shared:
        add(ep.model, "platform", str(ep.id), ep.is_default)
    if settings.default_model:
        add(settings.default_model, "env_default", None, True)
    return {"models": models}


@router.get("/auto-pool")
async def auto_pool_models(user: User = Depends(get_current_user)) -> dict:
    """网关 auto 池主力模型列表(会话模型选择器数据源,T18.19)。

    代理网关 GET /v1/models?auto_pool=true(黑名单后的真实调度池),
    平台不自维护池清单(会漂移);网关不可达返回明确错误。
    """
    from agentplatform.core.llm.http_client import make_http_client

    base = settings.openai_base_url.rstrip("/")
    key = settings.openai_api_key
    if not base or not key:
        raise HTTPException(status_code=503, detail="未配置网关端点")
    async with make_http_client(timeout=15) as c:
        resp = await c.get(
            f"{base}/models?auto_pool=true",
            headers={"Authorization": f"Bearer {key}"},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"网关返回 {resp.status_code}")
    ids = [m.get("id") for m in resp.json().get("data", []) if m.get("id")]
    return {"models": ids}


# ── 模型供应商(M29/需求 018/设计 023 §4)───────────────────

from pydantic import BaseModel, Field

from agentplatform.core.llm import provider_service


class ProviderCreate(BaseModel):
    name: str = ""
    preset: str = "custom"
    base_url: str = Field(min_length=1, max_length=300)
    api_key: str = Field(min_length=1, max_length=500)
    models: list[str] = Field(default_factory=list, max_length=100)


class ProviderKeyIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


class ProviderModelsIn(BaseModel):
    models: list[str] = Field(default_factory=list, max_length=100)


class ProviderRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


@router.get("/providers")
async def my_providers(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """我的供应商列表(含模型分组;Key 不回显)+ 预设目录。"""
    return {
        "providers": await provider_service.list_providers(session, str(user.id)),
        "presets": provider_service.PROVIDER_PRESETS,
    }


@router.post("/providers", status_code=201)
async def add_provider(
    payload: ProviderCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """添加供应商:保存即验证并发现模型(失败可保存,响应带探测详情)。"""
    try:
        provider, probe = await provider_service.create_provider(
            session,
            user_id=str(user.id), name=payload.name, preset=payload.preset,
            base_url=payload.base_url, api_key=payload.api_key, models=payload.models,
        )
    except provider_service.ProviderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await session.commit()
    return {"id": str(provider.id), "name": provider.name, "status": provider.status, **probe}


@router.patch("/providers/{provider_id}")
async def patch_provider(
    provider_id: uuid.UUID,
    payload: ProviderRenameIn | ProviderKeyIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """改名 或 换 Key(重验证,既有模型保留)。"""
    try:
        if isinstance(payload, ProviderKeyIn):
            provider, probe = await provider_service.rotate_key(
                session, str(user.id), provider_id, payload.api_key
            )
            await session.commit()
            return {"id": str(provider.id), "status": provider.status, **probe}
        provider = await provider_service.rename_provider(
            session, str(user.id), provider_id, payload.name
        )
        await session.commit()
        return {"id": str(provider.id), "name": provider.name}
    except provider_service.ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/providers/{provider_id}", status_code=204)
async def remove_provider(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    ok = await provider_service.delete_provider(session, str(user.id), provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="供应商不存在")
    await session.commit()


@router.post("/providers/{provider_id}/models")
async def set_provider_models(
    provider_id: uuid.UUID,
    payload: ProviderModelsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """勾选落库(全量覆盖该供应商模型集)。"""
    try:
        await provider_service.set_models(session, str(user.id), provider_id, payload.models)
    except provider_service.ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return {"ok": True, "count": len(payload.models)}


@router.get("/providers/{provider_id}/models")
async def rediscover(
    provider_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """重拉上游模型列表(候选,不落库;同时刷新验证状态)。"""
    try:
        result = await provider_service.rediscover_models(session, str(user.id), provider_id)
    except provider_service.ProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await session.commit()
    return result
