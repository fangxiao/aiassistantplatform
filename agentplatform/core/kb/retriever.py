"""向量检索后端(设计 008 §1/§3.3,T12.6,ADR 0004)。

Retriever 接口收口检索调用;PgVectorRetriever 为默认实现(cosine + join 过滤
软删文档)。替换独立向量库时仅新增实现,不改上层 API(NFR-3)。
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.kb.model import KbChunk, KbDocument, KbDocumentStatus, KnowledgeBase


@dataclass(frozen=True)
class RetrievedChunk:
    """检索命中片段(溯源字段全量保留,需求 005 §F2.3)。"""

    kb_id: uuid.UUID
    kb_name: str
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    score: float
    text: str
    source_span: dict


class Retriever(Protocol):
    """检索后端接口。"""

    async def search(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        kb_ids: list[uuid.UUID],
        top_k: int,
    ) -> list[RetrievedChunk]: ...


class PgVectorRetriever:
    """pgvector cosine 实现;kb_id 白名单过滤 + join 过滤软删文档。"""

    async def search(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        kb_ids: list[uuid.UUID],
        top_k: int,
    ) -> list[RetrievedChunk]:
        if not kb_ids or top_k <= 0:
            return []
        stmt = (
            select(
                KbChunk.kb_id,
                KnowledgeBase.name,
                KbChunk.document_id,
                KbDocument.filename,
                KbChunk.chunk_index,
                KbChunk.embedding.cosine_distance(query_embedding).label("distance"),
                KbChunk.text,
                KbChunk.source_span,
            )
            .join(KbDocument, KbChunk.document_id == KbDocument.id)
            .join(KnowledgeBase, KbChunk.kb_id == KnowledgeBase.id)
            .where(
                KbChunk.kb_id.in_(kb_ids),  # 白名单即授权来源(设计 008 §3.3)
                KbDocument.status != KbDocumentStatus.deleted,  # 软删即时过滤(需求 F1.4)
                KnowledgeBase.status == "active",
            )
            .order_by("distance")
            .limit(top_k)
        )
        rows = await db.execute(stmt)
        return [
            RetrievedChunk(
                kb_id=r.kb_id,
                kb_name=r.name,
                document_id=r.document_id,
                document_name=r.filename,
                chunk_index=r.chunk_index,
                score=1.0 - float(r.distance),
                text=r.text,
                source_span=dict(r.source_span or {}),
            )
            for r in rows
        ]


retriever: Retriever = PgVectorRetriever()
"""模块级默认后端(NFR-3 切换点;测试可替换)。"""
