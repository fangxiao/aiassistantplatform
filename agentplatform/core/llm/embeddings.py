"""embedding 客户端(M12,设计 008 §3.2 / T12.4)。

端点复用 llm_endpoints(endpoint_type=embedding),密钥管理同 crypto;
无专用端点时回退 .env 主端点 + settings.kb_embedding_model。
非流式 POST /embeddings,批量(batch)调用。
"""

import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.llm.crypto import encrypt
from agentplatform.core.llm.http_client import make_http_client
from agentplatform.core.llm.model import EndpointType, LlmEndpoint
from agentplatform.core.llm.service import get_api_key

EMBED_BATCH_SIZE = 64  # 单批文本数上限(设计 008 §6)


class EmbeddingError(Exception):
    """embedding 调用失败。"""


async def resolve_embedding_endpoint(db: AsyncSession) -> LlmEndpoint:
    """解析 embedding 端点:端点表 embedding 类型优先,回退 .env 主端点。"""
    row = await db.scalars(
        select(LlmEndpoint)
        .where(LlmEndpoint.endpoint_type == EndpointType.embedding)
        .order_by(LlmEndpoint.is_default.desc(), LlmEndpoint.name)
        .limit(1)
    )
    endpoint = row.first()
    if endpoint is not None:
        return endpoint

    if settings.openai_base_url and settings.openai_api_key and settings.kb_embedding_model:
        return LlmEndpoint(
            name="kb_env_fallback",
            base_url=settings.openai_base_url,
            model=settings.kb_embedding_model,
            api_key_enc=encrypt(settings.openai_api_key),
            is_default=False,
            endpoint_type=EndpointType.embedding,
        )
    raise EmbeddingError(
        "未配置 embedding 端点(llm_endpoints 增加 endpoint_type=embedding 条目,"
        "或设置 KB_EMBEDDING_MODEL 与主端点)"
    )


async def embed_texts(
    texts: list[str], endpoint: LlmEndpoint, transport: httpx.AsyncBaseTransport | None = None
) -> list[list[float]]:
    """批量向量化(自动分批);返回与输入等长的向量列表。"""
    vectors: list[list[float]] = []
    async with make_http_client(timeout=60.0, transport=transport) as client:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            vectors.extend(await _embed_batch(batch, endpoint, client))
    return vectors


async def _embed_batch(
    texts: list[str], endpoint: LlmEndpoint, client: httpx.AsyncClient
) -> list[list[float]]:
    """单批调用 OpenAI 兼容 /embeddings。"""
    try:
        resp = await client.post(
            f"{endpoint.base_url.rstrip('/')}/embeddings",
            json={"model": endpoint.model, "input": texts},
            headers={"Authorization": f"Bearer {get_api_key(endpoint)}"},
        )
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"embedding 请求失败: {exc}") from exc
    if resp.status_code != 200:
        raise EmbeddingError(
            f"embedding 端点返回 {resp.status_code}: {resp.text[:300]}"
        )
    data = resp.json().get("data", [])
    if len(data) != len(texts):
        raise EmbeddingError(f"embedding 返回条数不符: 期望 {len(texts)},得到 {len(data)}")
    # 按 index 还原顺序(部分端点不保证有序)
    ordered = sorted(data, key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in ordered]


def estimate_tokens(text: str) -> int:
    """粗略 token 估算(中英混合):CJK 字符 ≈ 1 token/字,其余 ≈ 0.25 token/字符。

    仅用于切分长度控制,不追求精确(pipeline 预算用,设计 008 §6)。
    """
    cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
    return max(1, cjk + (len(text) - cjk) // 4)


async def embed_with_concurrency(
    batches: list[list[str]], endpoint: LlmEndpoint
) -> list[list[float]]:
    """并发执行多批(限流 4),按原顺序拼接。"""
    sem = asyncio.Semaphore(4)

    async def run(batch: list[str]) -> list[list[float]]:
        async with sem, make_http_client(timeout=60.0) as client:
            return await _embed_batch(batch, endpoint, client)

    results = await asyncio.gather(*[run(b) for b in batches])
    return [v for batch in results for v in batch]
