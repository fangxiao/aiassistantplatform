"""知识库 API(设计 008 §7,T12.8/T12.9)。

统一错误 {error:{code,message}}(main.py 异常处理器);鉴权同 registry/chat。
publish:公共库版本发布,事务内登记 skill_tools(kind=kb,ADR 0005)。
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.db.session import get_session
from agentplatform.core.kb import pipeline as kb_pipeline
from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KbDocument, KbVisibility, KnowledgeBase
from agentplatform.core.kb.search_tool import run_kb_search
from agentplatform.core.llm.embeddings import resolve_embedding_endpoint
from agentplatform.core.registry.model import SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import register

router = APIRouter(prefix="/kb", tags=["kb"])


class KbCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=2, max_length=64)
    visibility: KbVisibility = KbVisibility.private
    description: str | None = None


class KbUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class KbOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    slug: str
    visibility: KbVisibility
    version: str
    description: str | None
    status: str
    doc_count: int
    chunk_count: int
    size_bytes: int


class KbDocOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    mime: str
    size_bytes: int
    status: str
    error: str | None


class KbSearchIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class KbPublishIn(BaseModel):
    version: str | None = None  # 缺省自动 bump patch


def _http_error(exc: kb_service.KbError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "kb_error", "message": str(exc)})


async def _get_visible_kb(
    kb_id: uuid.UUID, db: AsyncSession, user: User
) -> KnowledgeBase:
    kb = await kb_service.get_kb(db, kb_id)
    if kb is None or not kb_service.can_read(kb, str(user.id)):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "知识库不存在"}
        )
    return kb


@router.get("/kbs", response_model=list[KbOut])
async def list_kbs(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[KbOut]:
    """当前用户可见库(private 自己 + public)。"""
    rows = await kb_service.list_visible_kbs(db, str(user.id))
    return [KbOut.model_validate(r) for r in rows]


@router.post("/kbs", response_model=KbOut, status_code=201)
async def create_kb(
    payload: KbCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbOut:
    """新建库(public 仅 developer 角色)。"""
    try:
        kb = await kb_service.create_kb(
            db,
            name=payload.name,
            slug=payload.slug,
            owner=user,
            visibility=payload.visibility,
            description=payload.description,
        )
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return KbOut.model_validate(kb)


@router.patch("/kbs/{kb_id}", response_model=KbOut)
async def update_kb(
    kb_id: uuid.UUID,
    payload: KbUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbOut:
    """改名/描述。"""
    kb = await _get_visible_kb(kb_id, db, user)
    try:
        kb = await kb_service.update_kb(db, kb, user, name=payload.name, description=payload.description)
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return KbOut.model_validate(kb)


@router.delete("/kbs/{kb_id}")
async def delete_kb(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除库(级联清理文档与片段)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    try:
        await kb_service.delete_kb(db, kb, user)
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return {"ok": True}


@router.post("/kbs/{kb_id}/documents", response_model=KbDocOut, status_code=201)
async def upload_document(
    kb_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbDocOut:
    """上传文档(md/txt/pdf);异步处理,状态见 GET documents。"""
    kb = await _get_visible_kb(kb_id, db, user)
    content = await file.read()
    try:
        doc = await kb_service.add_document(
            db, kb, user,
            filename=file.filename or "untitled.txt",
            mime=file.content_type or "application/octet-stream",
            content=content,
        )
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    kb_pipeline.enqueue_document(doc.id)  # 落库后入队,worker 消费
    return KbDocOut.model_validate(doc)


@router.get("/kbs/{kb_id}/documents", response_model=list[KbDocOut])
async def list_documents(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[KbDocOut]:
    """文档列表(含处理状态)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    rows = await kb_service.list_documents(db, kb.id)
    return [KbDocOut.model_validate(r) for r in rows]


@router.delete("/kbs/{kb_id}/documents/{doc_id}")
async def delete_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """删除文档(软删,检索即时过滤)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    doc = await db.get(KbDocument, doc_id)
    if doc is None or doc.kb_id != kb.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "文档不存在"})
    try:
        await kb_service.soft_delete_document(db, kb, doc, user)
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return {"ok": True}


@router.post("/kbs/{kb_id}/documents/{doc_id}/retry", response_model=KbDocOut)
async def retry_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbDocOut:
    """失败重试(重新入队)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    doc = await db.get(KbDocument, doc_id)
    if doc is None or doc.kb_id != kb.id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "文档不存在"})
    if not await kb_pipeline.retry_document(db, doc):
        raise HTTPException(
            status_code=400,
            detail={"code": "kb_error", "message": "仅 failed 状态可重试"},
        )
    await db.commit()
    return KbDocOut.model_validate(doc)


@router.post("/kbs/{kb_id}/search")
async def search_kb(
    kb_id: uuid.UUID,
    payload: KbSearchIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """检索测试(WebUI 调试框;与 tool:kb_search 同一检索链路)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    raw = await run_kb_search(db, [kb.id], {"query": payload.query, "top_k": payload.top_k})
    return json.loads(raw)


@router.post("/kbs/{kb_id}/publish", response_model=KbOut)
async def publish_kb(
    kb_id: uuid.UUID,
    payload: KbPublishIn | None = None,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbOut:
    """发布公共库版本(仅 developer 角色;bump semver + 登记 skill_tools kind=kb)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    if user.role != UserRole.developer:
        raise HTTPException(
            status_code=403, detail={"code": "forbidden", "message": "仅 developer 角色可发布公共知识库"}
        )
    kb.visibility = KbVisibility.public
    new_version = (payload.version if payload else None) or _bump_version(kb.version)
    try:
        # 记录 embedding 模型进注册表 schema(设计 008 §10 风险 1);未配置端点时发布仍可进行
        embedding_model = (await resolve_embedding_endpoint(db)).model
    except Exception:  # noqa: BLE001
        embedding_model = ""
    # 事务内登记注册表行(ADR 0005):kb 资源无实现,行只承担依赖解析
    await register(
        db,
        resource_id=f"kb:{kb.slug}",
        kind=SkillToolKind.kb,
        name=kb.slug,
        version=new_version,
        source=SkillToolSource.shared,
        schema_={"embedding_model": embedding_model, "doc_count": kb.doc_count},
        impl_path=None,
        description=kb.description or kb.name,
        owner_id=str(user.id),
    )
    kb.version = new_version
    await db.commit()
    return KbOut.model_validate(kb)


def _bump_version(version: str) -> str:
    """patch 自增(0.0.0 → 0.0.1)。"""
    try:
        parts = [int(p) for p in version.split(".")]
        parts[-1] += 1
        return ".".join(str(p) for p in parts)
    except ValueError:
        return "0.0.1"
