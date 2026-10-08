"""模型供应商服务(M29/需求 018/设计 023 §2-§3)。

预设常量 / CRUD / 连通性验证与模型发现 / 级联删除。
验证三态:verified(拉到模型列表)/ unverified(失败可保存,内网/非标)/
invalid 由前端按 401 提示,不单独落库语义(status=unverified + 原因返回)。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.llm import crypto
from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.llm.provider_model import LlmProvider

# 供应商预设(设计 023 §2):前端选择器数据源,base_url 预填可改
PROVIDER_PRESETS: dict[str, dict] = {
    "volcark": {"label": "火山方舟", "base_url": "https://ark.cn-beijing.volces.com/api/v3"},
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1"},
    "siliconflow": {"label": "硅基流动", "base_url": "https://api.siliconflow.cn/v1"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"label": "Anthropic(兼容层)", "base_url": "https://api.anthropic.com/v1"},
    "custom": {"label": "自定义", "base_url": ""},
}


class ProviderError(Exception):
    """供应商操作错误(message 直接面向用户)。"""


async def list_providers(session: AsyncSession, user_id: str) -> list[dict]:
    """我的供应商列表(含各供应商模型数与模型名,选择器分组用)。"""
    rows = (
        await session.scalars(
            select(LlmProvider)
            .where(LlmProvider.user_id == str(user_id))
            .order_by(LlmProvider.created_at.desc())
        )
    ).all()
    if not rows:
        return []
    models = (
        await session.scalars(
            select(LlmEndpoint).where(
                LlmEndpoint.owner_id == str(user_id),
                LlmEndpoint.provider_id.in_([p.id for p in rows]),
            )
        )
    ).all()
    by_provider: dict[str, list[dict]] = {}
    for m in models:
        by_provider.setdefault(str(m.provider_id), []).append(
            {"model": m.model, "endpoint_id": str(m.id), "is_default": m.is_default}
        )
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "preset": p.preset,
            "base_url": p.base_url,
            "status": p.status,
            "last_checked_at": p.last_checked_at.isoformat() if p.last_checked_at else None,
            "has_key": True,
            "models": by_provider.get(str(p.id), []),
        }
        for p in rows
    ]


async def _probe_models(base_url: str, api_key: str) -> tuple[bool, list[str], str]:
    """连通性验证 + 模型发现:GET {base}/models(5s 超时)。

    返回 (ok, model_ids, message);ok=False 时 message 说明原因(401=key 错误)。
    """
    from agentplatform.core.llm.http_client import make_http_client

    url = base_url.rstrip("/") + "/models"
    try:
        async with make_http_client(timeout=5) as c:
            resp = await c.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except Exception as exc:  # noqa: BLE001 网络层任何异常都归为未验证
        return False, [], f"连接失败:{type(exc).__name__}(内网或非标准上游可保存后手填模型)"
    if resp.status_code == 401:
        return False, [], "API Key 无效(401)"
    if resp.status_code != 200:
        return False, [], f"上游返回 {resp.status_code}"
    try:
        data = resp.json()
        ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
    except Exception:  # noqa: BLE001
        return True, [], "已连通,但响应不是标准模型列表(可手填模型名)"
    return True, ids, ""


async def create_provider(
    session: AsyncSession, *, user_id: str, name: str, preset: str,
    base_url: str, api_key: str, models: list[str] | None = None,
) -> tuple[LlmProvider, dict]:
    """新建供应商并验证;models 为勾选的模型 id 列表(验证成功场景)。

    验证失败不阻断(需求 018 决策 2):status=unverified 落库,响应带探测详情。
    """
    if preset not in PROVIDER_PRESETS:
        raise ProviderError(f"未知预设:{preset!r}")
    if not base_url.strip() or not api_key.strip():
        raise ProviderError("base_url 与 API Key 不能为空")
    ok, found, msg = await _probe_models(base_url, api_key)
    provider = LlmProvider(
        user_id=str(user_id), name=name.strip()[:60] or PROVIDER_PRESETS[preset]["label"],
        preset=preset, base_url=base_url.strip(),
        api_key_enc=crypto.encrypt(api_key.strip()),
        status="verified" if ok else "unverified",
        last_checked_at=datetime.now(UTC),
    )
    session.add(provider)
    await session.flush()
    # 模型落库:优先调用方勾选(与 found 的交集防御);验证失败时 models 通常为空
    picked = [m for m in (models or []) if not found or m in set(found)] or (
        found[:20] if ok and found else []
    )
    await _sync_models(session, provider, picked)
    return provider, {"verified": ok, "models_found": found, "message": msg}


async def _sync_models(session: AsyncSession, provider: LlmProvider, models: list[str]) -> None:
    """全量覆盖该供应商的模型端点(设计 023 §4 POST models 语义)。"""
    await session.execute(
        delete(LlmEndpoint).where(LlmEndpoint.provider_id == provider.id)
    )
    for m in models:
        session.add(
            LlmEndpoint(
                name=f"{provider.name}:{m}"[:120],
                base_url=provider.base_url,
                model=m,
                api_key_enc=provider.api_key_enc,  # 与供应商同一密文
                owner_id=provider.user_id,
                provider_id=provider.id,
            )
        )
    await session.flush()


async def rotate_key(
    session: AsyncSession, user_id: str, provider_id: uuid.UUID, api_key: str
) -> tuple[LlmProvider, dict]:
    """换 Key 并重验证(既有模型集保留)。"""
    provider = await _owned(session, user_id, provider_id)
    ok, found, msg = await _probe_models(provider.base_url, api_key)
    provider.api_key_enc = crypto.encrypt(api_key.strip())
    provider.status = "verified" if ok else "unverified"
    provider.last_checked_at = datetime.now(UTC)
    # 换 Key 后既有端点的密文同步刷新
    key_enc = provider.api_key_enc
    rows = (
        await session.scalars(
            select(LlmEndpoint).where(LlmEndpoint.provider_id == provider.id)
        )
    ).all()
    for r in rows:
        r.api_key_enc = key_enc
    await session.flush()
    return provider, {"verified": ok, "models_found": found, "message": msg}


async def set_models(
    session: AsyncSession, user_id: str, provider_id: uuid.UUID, models: list[str]
) -> None:
    provider = await _owned(session, user_id, provider_id)
    await _sync_models(session, provider, models)


async def rediscover_models(
    session: AsyncSession, user_id: str, provider_id: uuid.UUID
) -> dict:
    """重拉上游模型列表(不落库,返回候选;同时刷新验证状态)。"""
    provider = await _owned(session, user_id, provider_id)
    ok, found, msg = await _probe_models(provider.base_url, crypto.decrypt(provider.api_key_enc))
    provider.status = "verified" if ok else "unverified"
    provider.last_checked_at = datetime.now(UTC)
    await session.flush()
    return {"verified": ok, "models_found": found, "message": msg}


async def rename_provider(
    session: AsyncSession, user_id: str, provider_id: uuid.UUID, name: str
) -> LlmProvider:
    provider = await _owned(session, user_id, provider_id)
    provider.name = name.strip()[:60] or provider.name
    await session.flush()
    return provider


async def delete_provider(session: AsyncSession, user_id: str, provider_id: uuid.UUID) -> bool:
    """删除供应商(级联删其模型端点;设计 023 §1)。"""
    provider = await session.scalar(
        select(LlmProvider).where(
            LlmProvider.id == provider_id, LlmProvider.user_id == str(user_id)
        )
    )
    if provider is None:
        return False
    await session.execute(
        delete(LlmEndpoint).where(LlmEndpoint.provider_id == provider.id)
    )
    await session.delete(provider)
    await session.flush()
    return True


async def _owned(session: AsyncSession, user_id: str, provider_id: uuid.UUID) -> LlmProvider:
    provider = await session.get(LlmProvider, provider_id)
    if provider is None or provider.user_id != str(user_id):
        raise ProviderError("供应商不存在")
    return provider
