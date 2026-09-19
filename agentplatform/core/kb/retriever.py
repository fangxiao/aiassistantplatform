"""向量检索后端(设计 008 §1/§3.3,T12.6,ADR 0004)。

Retriever 接口收口检索调用;PgVectorRetriever 为默认实现(cosine + join 过滤
软删文档)。替换独立向量库时仅新增实现,不改上层 API(NFR-3)。
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import Text, bindparam, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text

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
        query_text: str | None = None,
    ) -> list[RetrievedChunk]: ...


class PgVectorRetriever:
    """混合检索实现(打磨①):向量 cosine + trgm 关键词双路召回 → RRF 融合。

    语义路解决"意思相近";关键词路(similarity)兜住专有名词/编号/型号——
    纯向量对这类 token 命中率差。Reciprocal Rank Fusion 融合两路排名,
    不依赖分数标定。kb_id 白名单 + 软删过滤与单路时一致(设计 008 §3.3)。
    """

    _RECALL = 20  # 每路召回条数(融合后取 top_k)

    async def search(
        self,
        db: AsyncSession,
        query_embedding: list[float],
        kb_ids: list[uuid.UUID],
        top_k: int,
        query_text: str | None = None,
    ) -> list[RetrievedChunk]:
        if not kb_ids or top_k <= 0:
            return []

        base_cols = (
            KbChunk.id,
            KbChunk.kb_id,
            KnowledgeBase.name,
            KbChunk.document_id,
            KbDocument.filename,
            KbChunk.chunk_index,
            KbChunk.text,
            KbChunk.source_span,
        )
        base_where = (
            KbChunk.kb_id.in_(kb_ids),  # 白名单即授权来源(设计 008 §3.3)
            KbDocument.status != KbDocumentStatus.deleted,  # 软删即时过滤(需求 F1.4)
            KnowledgeBase.status == "active",
        )
        base_joins = (
            KbChunk.document_id == KbDocument.id,
            KbChunk.kb_id == KnowledgeBase.id,
        )

        # 1) 向量语义路
        vec_stmt = (
            select(
                *base_cols,
                KbChunk.embedding.cosine_distance(query_embedding).label("distance"),
            )
            .join(KbDocument, base_joins[0])
            .join(KnowledgeBase, base_joins[1])
            .where(*base_where)
            .order_by("distance")
            .limit(self._RECALL)
        )
        vec_rows = list(await db.execute(vec_stmt))

        # 2) 关键词 trgm 路(有 query_text 时;兜住专名/编号)
        kw_rows = []
        if query_text and query_text.strip():
            # 中文 trigram 短查询与默认阈值 0.3 不匹配——放宽到 0.1(事务内,不影响全局)
            await db.execute(sa_text("SET LOCAL pg_trgm.similarity_threshold = 0.1"))
            kw_stmt = (
                select(*base_cols)
                .join(KbDocument, base_joins[0])
                .join(KnowledgeBase, base_joins[1])
                .where(
                    *base_where,
                    # trgm 相似度算子(gin 索引命中);CAST 在 SQL 内写死规避驱动参数类型
                    sa_text("kb_chunks.text % CAST(:kwq AS TEXT)").bindparams(
                        bindparam("kwq", value=query_text.strip())
                    ),
                )
                .limit(self._RECALL)
            )
            kw_rows = list(await db.execute(kw_stmt))

        # 3) RRF 融合(排名倒数加权,无分数标定依赖)
        rrf: dict[int, float] = {}
        meta: dict[int, dict] = {}
        for rows in (vec_rows, kw_rows):
            for rank, r in enumerate(rows):
                rrf[r.id] = rrf.get(r.id, 0.0) + 1.0 / (rank + 60)  # k=60 常规值
                if r.id not in meta:
                    meta[r.id] = {
                        "kb_id": r.kb_id,
                        "kb_name": r.name,
                        "document_id": r.document_id,
                        "document_name": r.filename,
                        "chunk_index": r.chunk_index,
                        "text": r.text,
                        "source_span": dict(r.source_span or {}),
                        "vec_score": 1.0 - float(r.distance) if hasattr(r, "distance") else None,
                    }
                elif hasattr(r, "distance"):
                    meta[r.id]["vec_score"] = 1.0 - float(r.distance)

        ordered = sorted(rrf.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [
            RetrievedChunk(
                kb_id=m["kb_id"],
                kb_name=m["kb_name"],
                document_id=m["document_id"],
                document_name=m["document_name"],
                chunk_index=m["chunk_index"],
                score=round(rrf_score, 4),
                text=m["text"],
                source_span=m["source_span"],
            )
            for cid, rrf_score in ordered
            for m in [meta[cid]]
        ]


retriever: Retriever = PgVectorRetriever()
"""模块级默认后端(NFR-3 切换点;测试可替换)。"""
