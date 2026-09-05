"""知识库测试(M12,T12.14)。

覆盖:库服务鉴权/配额、切分、检索过滤、kb_search 权限红线(请求参数不是授权来源)、
allowed 范围组装、pipeline 状态机;集成部分覆盖需求 005 §5 验收 1/3/4。
"""

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.kb import pipeline as kb_pipeline
from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KbDocument, KbDocumentStatus
from agentplatform.core.kb.retriever import retriever
from agentplatform.core.kb.search_tool import resolve_allowed_kb_ids, run_kb_search
from agentplatform.core.registry.model import SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import register

# ---------------------------------------------------------------- fixtures


@pytest.fixture
async def dev_user(session: AsyncSession):
    return await create_user(session, f"dev-{uuid.uuid4()}@test.dev", "password123", UserRole.developer)


@pytest.fixture
async def normal_user(session: AsyncSession):
    return await create_user(session, f"u-{uuid.uuid4()}@test.dev", "password123", UserRole.user)


async def _make_kb(session, owner, slug="docs_a", visibility="private"):
    from agentplatform.core.kb.model import KbVisibility

    return await kb_service.create_kb(
        session, name=slug, slug=slug, owner=owner, visibility=KbVisibility(visibility)
    )


# ---------------------------------------------------------------- 库服务(需求 F1/F6)


async def test_create_kb_slug_and_visibility(session, dev_user, normal_user):
    kb = await _make_kb(session, dev_user, slug="docs_ok")
    assert kb.visibility.value == "private"
    with pytest.raises(kb_service.KbError):  # slug 唯一
        await _make_kb(session, normal_user, slug="docs_ok")
    with pytest.raises(kb_service.KbError):  # slug 格式
        await kb_service.create_kb(
            session, name="x", slug="Bad-Slug", owner=dev_user
        )
    with pytest.raises(kb_service.KbError):  # public 仅 developer
        await kb_service.create_kb(
            session,
            name="pub",
            slug="pub_docs",
            owner=normal_user,
            visibility=kb_service.KbVisibility.public,
        )


async def test_can_read_private_isolated(session, dev_user, normal_user):
    kb = await _make_kb(session, dev_user)
    assert kb_service.can_read(kb, str(dev_user.id))
    assert not kb_service.can_read(kb, str(normal_user.id))  # 验收 3:他人 private 不可读


async def test_upload_document_validation_and_dedupe(session, dev_user):
    kb = await _make_kb(session, dev_user)
    doc = await kb_service.add_document(
        db=session, kb=kb, user=dev_user,
        filename="a.md", mime="text/markdown", content=b"hello",
    )
    assert doc.status == KbDocumentStatus.pending
    with pytest.raises(kb_service.KbError):  # 类型限制
        await kb_service.add_document(
            db=session, kb=kb, user=dev_user,
            filename="a.exe", mime="application/octet-stream", content=b"x",
        )
    with pytest.raises(kb_service.KbError):  # hash 去重
        await kb_service.add_document(
            db=session, kb=kb, user=dev_user,
            filename="a2.md", mime="text/markdown", content=b"hello",
        )
    assert kb.doc_count == 1


# ---------------------------------------------------------------- 切分


def test_chunk_text_offsets_reconstruct():
    text = "段落一内容。\n\n段落二比较长," * 3 + "结尾。"
    spans = kb_pipeline.chunk_text(text, target_tokens=8, overlap_tokens=0)
    assert spans
    for start, end in spans:
        assert 0 <= start < end <= len(text)
        assert text[start:end].strip()  # 不含纯空白片段


def test_chunk_text_long_paragraph_hard_split():
    text = "字" * 2000
    spans = kb_pipeline.chunk_text(text, target_tokens=100, overlap_tokens=10)
    assert len(spans) > 1
    assert spans[0][0] == 0 and spans[-1][1] == 2000


# ---------------------------------------------------------------- 检索与权限红线(验收 3/4)


async def _seed_chunks(session, kb, texts):
    doc = KbDocument(
        kb_id=kb.id, filename="doc.md", mime="text/markdown",
        size_bytes=10, content_hash=uuid.uuid4().hex, status=KbDocumentStatus.ready,
    )
    session.add(doc)
    await session.flush()
    from agentplatform.core.kb.model import KbChunk

    dim = settings.kb_embedding_dim
    for i, t in enumerate(texts):
        session.add(KbChunk(
            document_id=doc.id, kb_id=kb.id, chunk_index=i, text=t,
            source_span={"start": 0, "end": len(t)}, token_count=1,
            embedding=[0.1 * (j % 10) + i for j in range(dim)],
        ))
    await session.flush()
    return doc


async def test_retriever_whitelist_and_deleted_filter(session, dev_user, normal_user):
    kb1 = await _make_kb(session, dev_user, slug="kb1_")
    kb2 = await _make_kb(session, normal_user, slug="kb2_")
    await _seed_chunks(session, kb1, ["alpha content"])
    await _seed_chunks(session, kb2, ["beta content"])
    dim = settings.kb_embedding_dim
    vec = [0.1 * (j % 10) for j in range(dim)]

    hits = await retriever.search(session, vec, [kb1.id], 5)
    assert len(hits) == 1 and hits[0].text == "alpha content"  # 白名单外不可见

    # 软删后立即不可检索(验收 4)
    doc = (await kb_service.list_documents(session, kb1.id))[0]
    await kb_service.soft_delete_document(session, kb1, doc, dev_user)
    assert await retriever.search(session, vec, [kb1.id], 5) == []


async def test_kb_search_request_ids_not_authorization(session, dev_user, normal_user):
    """权限红线(设计 008 §3.3):请求参数 kb_ids 永不作为授权来源。"""
    kb_mine = await _make_kb(session, dev_user, slug="mine_")
    await _seed_chunks(session, kb_mine, ["secret secret"])
    foreign = await _make_kb(session, normal_user, slug="foreign_")
    dim = settings.kb_embedding_dim

    class FakeEndpoint:
        base_url = "http://fake"
        model = "fake"
        api_key_enc = "k"

    import agentplatform.core.kb.search_tool as st

    async def fake_embed(texts, endpoint, transport=None):
        return [[0.1 * (j % 10) for j in range(dim)] for _ in texts]

    async def fake_resolve(db):
        return FakeEndpoint()

    orig_embed, orig_resolve = st.embed_texts, st.resolve_embedding_endpoint
    st.embed_texts, st.resolve_embedding_endpoint = fake_embed, fake_resolve
    try:
        # allowed 仅 mine;请求里塞 foreign 的 id → 被忽略,不泄露 foreign 内容
        raw = await run_kb_search(
            session, [kb_mine.id], {"query": "secret", "kb_ids": [str(foreign.id)]}
        )
        out = json.loads(raw)
        assert out["results"] == []
        # 完全未挂载:不返回任何内容
        raw2 = await run_kb_search(session, [], {"query": "secret"})
        assert json.loads(raw2)["results"] == []
    finally:
        st.embed_texts, st.resolve_embedding_endpoint = orig_embed, orig_resolve


async def test_resolve_allowed_plugin_public_dep_only(session, dev_user, normal_user):
    """插件静态依赖仅解析 public 库;private 依赖不进 allowed。"""
    pub = await kb_service.create_kb(
        session, name="pub", slug="pub_dep", owner=dev_user,
        visibility=kb_service.KbVisibility.public,
    )
    priv = await _make_kb(session, dev_user, slug="priv_dep")
    for slug in ("pub_dep", "priv_dep"):
        await register(
            session, resource_id=f"kb:{slug}", kind=SkillToolKind.kb,
            name=slug, version="1.0.0", source=SkillToolSource.shared,
            schema_={}, impl_path=None, description="",
        )
    mounted = [priv.id]  # 用户挂载自己的 private(合法)
    allowed = await resolve_allowed_kb_ids(
        session, mounted_kb_ids=mounted, plugin_manifest={
            "depends_on": ["kb:pub_dep@^1.0", "kb:priv_dep@^1.0"]
        },
    )
    assert pub.id in allowed and priv.id in allowed
    # 未挂载时 private 依赖不进 allowed
    allowed2 = await resolve_allowed_kb_ids(session, mounted_kb_ids=[], plugin_manifest={
        "depends_on": ["kb:priv_dep@^1.0"]
    })
    assert allowed2 == []


# ---------------------------------------------------------------- pipeline(验收 1 前半)


async def test_pipeline_process_document(session, dev_user, monkeypatch):
    kb = await _make_kb(session, dev_user)
    doc = await kb_service.add_document(
        db=session, kb=kb, user=dev_user,
        filename="note.md", mime="text/markdown",
        content="平台知识:agentplatform 是智能体平台。\n\n第二段内容。".encode(),
    )
    dim = settings.kb_embedding_dim

    async def fake_embed(texts, endpoint):
        return _fake_vectors(texts, dim)

    monkeypatch.setattr(kb_pipeline, "embed_texts", fake_embed)

    class FakeEndpoint:
        base_url = "http://fake"
        model = "fake"
        api_key_enc = "k"

    async def fake_resolve(db):
        return FakeEndpoint()

    monkeypatch.setattr(kb_pipeline, "resolve_embedding_endpoint", fake_resolve)
    result = await kb_pipeline.process_document(session, doc.id)
    assert result.status == KbDocumentStatus.ready
    assert kb.chunk_count >= 1
    # source_span 可回溯原文(溯源数据保留,需求 F2.3)
    from sqlalchemy import select

    from agentplatform.core.kb.model import KbChunk

    chunks = (await session.scalars(select(KbChunk).where(KbChunk.kb_id == kb.id))).all()
    full = "平台知识:agentplatform 是智能体平台。\n\n第二段内容。"
    for c in chunks:
        assert full[c.source_span["start"]:c.source_span["end"]] == c.text

    # 失败路径:内容为空 → failed + error 可重试
    doc2 = await kb_service.add_document(
        db=session, kb=kb, user=dev_user, filename="empty.md",
        mime="text/markdown", content=b"   ",
    )
    res2 = await kb_pipeline.process_document(session, doc2.id)
    assert res2.status == KbDocumentStatus.failed and res2.error
    assert await kb_pipeline.retry_document(session, res2)  # failed → 重置并重新入队
    assert res2.status == KbDocumentStatus.pending


def _fake_vectors(texts, dim):
    return [[0.01 * (len(t) % 50)] * dim for t in texts]


# ---------------------------------------------------------------- API 集成(验收 1/3 后半)


async def test_api_kb_flow_and_mount_isolation(session, client, dev_user, normal_user):
    """API 链路:建库→上传→(直接)处理→检索;挂载校验拒绝他人 private。"""
    # dev_user 建一个 private 库(不经 API,避免与 client 身份混淆)
    kb = await _make_kb(session, dev_user, slug="api_docs")

    r = await client.post(
        f"/api/kb/kbs/{kb.id}/documents",
        files={"file": ("a.md", "kb 知识内容正文", "text/markdown")},
    )
    assert r.status_code == 404  # client 身份 ≠ dev_user,private 库对其不可见(验收 3)

    # 他人 private 不可挂载
    r2 = await client.post(
        "/api/chat/sessions", json={"mounted_kb_ids": [str(kb.id)]}
    )
    assert r2.status_code == 404  # 挂载入口写入侧拒绝

    # client 自建库可上传,404 之前的成功路径
    r3 = await client.post("/api/kb/kbs", json={"name": "d", "slug": "api_docs_self"})
    assert r3.status_code == 201, r3.text
    own_kb_id = r3.json()["id"]
    r4 = await client.post(
        f"/api/kb/kbs/{own_kb_id}/documents",
        files={"file": ("a.md", "kb 知识内容正文", "text/markdown")},
    )
    assert r4.status_code == 201, r4.text

    # client fixture 默认 user 角色,不可发布 public
    r5 = await client.post(f"/api/kb/kbs/{own_kb_id}/publish")
    assert r5.status_code == 403


async def test_api_publish_and_registry_visible(session, client, session_user_dev):
    """发布后 kb: 资源进入注册表(验收 2 前半;registry 输出含 kb 行)。"""
    from agentplatform.core.registry.model import SkillToolKind
    from agentplatform.core.registry.service import list_public

    r = await client.post("/api/kb/kbs", json={"name": "p", "slug": "pub_api", "visibility": "public"})
    assert r.status_code == 201, r.text
    kb_id = r.json()["id"]
    r2 = await client.post(f"/api/kb/kbs/{kb_id}/publish")
    assert r2.status_code == 200, r2.text
    rows = await list_public(session, kind=SkillToolKind.kb)
    assert any(row.id == "kb:pub_api" for row in rows)  # 验收 5


@pytest.fixture
async def session_user_dev(session, client):
    """与 client fixture 相同身份但为 developer(client 覆盖的 user 固定角色)。"""
    # client fixture 的 get_current_user 覆盖返回其自建 user;这里直接提升该用户
    from sqlalchemy import select as _sel

    from agentplatform.core.auth.model import User

    row = (await session.scalars(_sel(User))).first()
    row.role = UserRole.developer
    await session.commit()
    return row
