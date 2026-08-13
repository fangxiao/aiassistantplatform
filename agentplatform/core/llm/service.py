"""LLM 端点管理服务(设计 004 §llm_endpoints)。

api_key 明文入、加密存储(见 crypto.py);取明文供 T3.2 客户端调用。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.llm.crypto import decrypt, encrypt
from agentplatform.core.llm.model import LlmEndpoint


async def list_endpoints(session: AsyncSession) -> list[LlmEndpoint]:
    rows = await session.scalars(select(LlmEndpoint).order_by(LlmEndpoint.name))
    return list(rows)


async def get_endpoint(
    session: AsyncSession, endpoint_id
) -> LlmEndpoint | None:
    return await session.get(LlmEndpoint, endpoint_id)


async def create_endpoint(
    session: AsyncSession,
    *,
    name: str,
    base_url: str,
    model: str,
    api_key: str,
    is_default: bool = False,
) -> LlmEndpoint:
    """新增端点;设默认时先清除其他默认。"""
    if is_default:
        await _clear_default(session)
    endpoint = LlmEndpoint(
        name=name,
        base_url=base_url,
        model=model,
        api_key_enc=encrypt(api_key),
        is_default=is_default,
    )
    session.add(endpoint)
    await session.flush()
    return endpoint


async def update_endpoint(
    session: AsyncSession,
    endpoint_id,
    *,
    name: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    is_default: bool | None = None,
) -> LlmEndpoint | None:
    """按需更新字段;不存在返回 None。设默认时先清除其他默认。"""
    endpoint = await get_endpoint(session, endpoint_id)
    if endpoint is None:
        return None
    if name is not None:
        endpoint.name = name
    if base_url is not None:
        endpoint.base_url = base_url
    if model is not None:
        endpoint.model = model
    if api_key is not None:
        endpoint.api_key_enc = encrypt(api_key)
    if is_default is True:
        await _clear_default(session)
        endpoint.is_default = True
    elif is_default is False:
        endpoint.is_default = False
    await session.flush()
    return endpoint


async def _clear_default(session: AsyncSession) -> None:
    rows = await session.scalars(select(LlmEndpoint).where(LlmEndpoint.is_default.is_(True)))
    for row in rows:
        row.is_default = False
    await session.flush()


def get_api_key(endpoint: LlmEndpoint) -> str:
    """返回端点明文 key(供客户端调用使用)。"""
    return decrypt(endpoint.api_key_enc)
