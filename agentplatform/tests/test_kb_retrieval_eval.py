"""检索质量评测集(打磨①):固定语料 + 标准查询,断言命中——检索策略的回归防线。

改检索参数(召回数/RRF k/相似度阈值)后跑此测试,确保不劣化。
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KbChunk, KbVisibility
from agentplatform.core.kb.retriever import retriever

DIM = 1024


def _vec(seed: int) -> list[float]:
    """确定性伪向量(同 seed 相似,不同 seed 弱相关)。"""
    import random

    r = random.Random(seed)
    return [r.random() for _ in range(DIM)]


# 评测语料:doc_id → (文本, 向量种子, 标准查询)
CORPUS = [
    ("连接器设计文档", "内容型连接器把外部系统内容增量同步进知识库,adapter 纯函数产出 FetchedDoc", 1,
     ["连接器的工作原理", "adapter 是什么"]),
    ("错误码对照表", "错误码 E4001 表示参数校验失败,E5002 表示网关超时,需要在请求侧重试", 2,
     ["E4001 是什么错误", "网关超时错误码"]),
    ("部署手册", "单机部署使用 docker compose,包含 pg redis api web 四个容器,执行 alembic 迁移", 3,
     ["怎么部署平台", "docker 部署步骤"]),
    ("请假制度", "年假每年 15 天,病假需要医院证明,事假扣薪", 4,
     ["年假有几天", "病假要什么证明"]),
]


@pytest.fixture
async def eval_kb(session: AsyncSession):
    user = await create_user(session, f"ev-{uuid.uuid4()}@test.dev", "p", UserRole.developer)
    kb = await kb_service.create_kb(
        session, name="eval", slug=f"eval{uuid.uuid4().hex[:8]}", owner=user,
        visibility=KbVisibility.private,
    )
    from agentplatform.core.kb.model import KbDocument, KbDocumentStatus

    doc_ids = {}
    for name, text, seed, _ in CORPUS:
        doc = KbDocument(
            kb_id=kb.id, filename=f"{name}.md", mime="text/markdown",
            size_bytes=len(text), content_hash=f"{seed}", status=KbDocumentStatus.ready,
        )
        session.add(doc)
        await session.flush()
        doc_ids[name] = doc.id
        session.add(
            KbChunk(
                document_id=doc.id, kb_id=kb.id, chunk_index=0, text=text,
                source_span={"start": 0, "end": len(text)}, token_count=10,
                embedding=_vec(seed),
            )
        )
    await session.flush()
    return kb, doc_ids


@pytest.mark.parametrize("doc_name,queries", [(n, q) for n, _, _, q in CORPUS])
async def test_recall_hit(session: AsyncSession, eval_kb, doc_name, queries) -> None:
    """每个标准查询的 top-3 必须命中所属文档(评测基线)。"""
    kb, doc_ids = eval_kb
    for q in queries:
        hits = await retriever.search(
            session, _vec(dict((n, s) for n, _, s, _ in CORPUS)[doc_name]),
            [kb.id], 3, query_text=q,
        )
        assert any(h.document_name == f"{doc_name}.md" for h in hits), (
            f"查询「{q}」未命中 {doc_name}: {[h.document_name for h in hits]}"
        )


async def test_keyword_path_catches_exact_code(session: AsyncSession, eval_kb) -> None:
    """专有编号(E4001)必须能被关键词路兜住——纯向量的弱项。"""
    kb, _ = eval_kb
    # 用无关向量(模拟向量路失效),只剩关键词路
    hits = await retriever.search(session, _vec(99), [kb.id], 3, query_text="E4001")
    assert any("E4001" in h.text for h in hits), "关键词路未兜住编号查询"
