"""知识库 API(设计 008 §7,T12.8/T12.9)。

统一错误 {error:{code,message}}(main.py 异常处理器);鉴权同 registry/chat。
publish:公共库版本发布,事务内登记 skill_tools(kind=kb,ADR 0005)。
"""

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.db.session import get_session
from agentplatform.core.kb import pipeline as kb_pipeline
from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.connectors import service as connector_service
from agentplatform.core.kb.model import (
    KbDataSource,
    KbDocument,
    KbVisibility,
    KnowledgeBase,
)
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
    can_write: bool = False  # 服务端计算(设计 008 §11.2),前端渲染收藏目标
    can_manage: bool = False  # 服务端计算(§12.2),数据源/成员等管理入口渲染用


class KbDocOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    kb_id: uuid.UUID
    filename: str
    mime: str
    size_bytes: int
    status: str
    error: str | None
    origin: str = "upload"
    source_app: str | None = None
    source_session_id: str | None = None
    source_message_id: str | None = None
    external_url: str | None = None  # 连接器文档的原文链接(设计 009)
    created_at: datetime | None = None


class KbSearchIn(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class KbPublishIn(BaseModel):
    version: str | None = None  # 缺省自动 bump patch


class DataSourceCreate(BaseModel):
    """新建数据源(连接器;设计 009 §7)。credentials 仅请求时可见,响应不回显。"""

    type: str
    name: str = Field(min_length=1, max_length=100)
    config: dict = {}
    credentials: dict | None = None
    poll_interval_minutes: int | None = Field(default=None, ge=1)


class DataSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    config: dict | None = None
    credentials: dict | None = None  # 传入则整体替换;不传保持不变
    poll_interval_minutes: int | None = Field(default=None, ge=1)
    status: str | None = None  # active / disabled


class DataSourceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    kb_id: uuid.UUID
    type: str
    name: str
    config: dict
    poll_interval_minutes: int | None
    status: str
    last_sync_at: datetime | None
    last_status: str
    last_error: str | None
    created_at: datetime


class SyncRunOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    data_source_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    added: int
    updated: int
    deleted: int
    skipped: int
    failed_docs: int
    error: str | None


class KbMemberAddIn(BaseModel):
    """按 email 添加成员(008 §12.3),避免暴露用户目录。"""

    email: str = Field(min_length=3, max_length=254)


class KbMemberOut(BaseModel):
    user_id: str
    email: str | None = None
    role: str = "member"
    created_at: datetime | None = None


class KbDocSource(BaseModel):
    """消费无关溯源;app 为自由字符串,平台不枚举消费方。"""

    app: str = Field(min_length=1, max_length=64)
    session_id: str | None = Field(default=None, max_length=128)
    message_id: str | None = Field(default=None, max_length=128)  # 同库幂等键


class KbDocFromTextIn(BaseModel):
    """文本直存(设计 008 §11.2):会话产出物收藏。"""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=5_000_000)
    mime: str = "text/markdown"  # text/markdown / text/plain / text/html
    source: KbDocSource | None = None


async def _kb_out(db: AsyncSession, kb: KnowledgeBase, user: User) -> KbOut:
    out = KbOut.model_validate(kb)
    out.can_write = await kb_service.can_write(db, kb, user)
    out.can_manage = kb_service.can_manage(kb, user)
    return out


def _http_error(exc: kb_service.KbError) -> HTTPException:
    return HTTPException(status_code=400, detail={"code": "kb_error", "message": str(exc)})


async def _get_visible_kb(
    kb_id: uuid.UUID, db: AsyncSession, user: User
) -> KnowledgeBase:
    kb = await kb_service.get_kb(db, kb_id)
    if kb is None or not await kb_service.can_read(db, kb, str(user.id)):
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
    return [await _kb_out(db, r, user) for r in rows]


@router.get("/public", response_model=list[KbOut])
async def list_public(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[KbOut]:
    """全员可读的公共库清单(助手挂载弹窗候选项;设计 008 §4.3)。"""
    rows = await kb_service.list_public_kbs(db)
    return [await _kb_out(db, r, user) for r in rows]


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
    return await _kb_out(db, kb, user)


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
    return await _kb_out(db, kb, user)


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


@router.post("/kbs/{kb_id}/documents/from-text", response_model=KbDocOut, status_code=201)
async def create_document_from_text(
    kb_id: uuid.UUID,
    payload: KbDocFromTextIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbDocOut:
    """文本直存(设计 008 §11):会话产出物收藏,复用 pipeline;source 消息级幂等。"""
    kb = await _get_visible_kb(kb_id, db, user)
    try:
        doc = await kb_service.add_document_from_text(
            db, kb, user,
            title=payload.title,
            content=payload.content,
            mime=payload.mime,
            source=payload.source.model_dump() if payload.source else None,
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


@router.get("/kbs/{kb_id}/members", response_model=list[KbMemberOut])
async def list_kb_members(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[KbMemberOut]:
    """成员列表(owner/成员可见,008 §12.3)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    rows = await kb_service.list_members(db, kb.id)
    out = []
    for row in rows:
        member_user = await db.get(User, uuid.UUID(row.user_id))
        out.append(
            KbMemberOut(
                user_id=row.user_id,
                email=member_user.email if member_user else None,
                role=row.role,
                created_at=row.created_at,
            )
        )
    return out


@router.post("/kbs/{kb_id}/members", response_model=KbMemberOut, status_code=201)
async def add_kb_member(
    kb_id: uuid.UUID,
    payload: KbMemberAddIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbMemberOut:
    """添加成员(仅 owner;按 email 解析用户,008 §12.3)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    member_user = await db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if member_user is None:
        raise HTTPException(
            status_code=400, detail={"code": "kb_error", "message": f"用户不存在: {payload.email}"}
        )
    try:
        row = await kb_service.add_member(db, kb, user, member=member_user)
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return KbMemberOut(user_id=row.user_id, email=member_user.email, role=row.role, created_at=row.created_at)


@router.delete("/kbs/{kb_id}/members/{member_user_id}")
async def remove_kb_member(
    kb_id: uuid.UUID,
    member_user_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """移除成员(仅 owner,008 §12.3)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    try:
        await kb_service.remove_member(db, kb, user, member_user_id=member_user_id)
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return {"ok": True}


@router.post("/kbs/{kb_id}/publish", response_model=KbOut)
async def publish_kb(
    kb_id: uuid.UUID,
    payload: KbPublishIn | None = None,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> KbOut:
    """发布公共库版本(仅 developer 角色;bump semver + 登记 skill_tools kind=kb)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    if kb.visibility == KbVisibility.shared:
        # shared 是团队资产,不进注册表(008 §12.1);防止误操作把团队库公开
        raise HTTPException(
            status_code=400,
            detail={"code": "kb_error", "message": "共享库不参与发布;如需公开请新建 public 库迁移内容"},
        )
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
    return await _kb_out(db, kb, user)


def _bump_version(version: str) -> str:
    """patch 自增(0.0.0 → 0.0.1)。"""
    try:
        parts = [int(p) for p in version.split(".")]
        parts[-1] += 1
        return ".".join(str(p) for p in parts)
    except ValueError:
        return "0.0.1"


# ---------------------------------------------------------------- 数据源(连接器,设计 009 §7)


async def _get_manageable_kb(
    kb_id: uuid.UUID, db: AsyncSession, user: User
) -> KnowledgeBase:
    """数据源管理鉴权:库须存在且当前用户有管理权(private/shared=owner,public=developer)。"""
    kb = await kb_service.get_kb(db, kb_id)
    if kb is None or not kb_service.can_manage(kb, user):
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "知识库不存在或无管理权"}
        )
    return kb


async def _get_source(
    kb_id: uuid.UUID, source_id: uuid.UUID, db: AsyncSession, user: User
) -> tuple[KnowledgeBase, KbDataSource]:
    kb = await _get_manageable_kb(kb_id, db, user)
    source = await connector_service.get_source(db, kb_id, source_id)
    if source is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "数据源不存在"}
        )
    return kb, source


def _source_out(source: KbDataSource) -> DataSourceOut:
    """enum -> value 手动序列化(避免 str-subclass enum 序列化歧义);不回显凭据。"""
    return DataSourceOut(
        id=source.id,
        kb_id=source.kb_id,
        type=source.type.value,
        name=source.name,
        config=source.config or {},
        poll_interval_minutes=source.poll_interval_minutes,
        status=source.status,
        last_sync_at=source.last_sync_at,
        last_status=source.last_status.value,
        last_error=source.last_error,
        created_at=source.created_at,
    )


@router.post("/kbs/{kb_id}/sources", response_model=DataSourceOut, status_code=201)
async def create_source(
    kb_id: uuid.UUID,
    payload: DataSourceCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DataSourceOut:
    """新建数据源(连接器);type 白名单与配置校验在 service 层。"""
    kb = await _get_manageable_kb(kb_id, db, user)
    try:
        source = await connector_service.create_source(
            db,
            kb.id,
            source_type=payload.type,
            name=payload.name,
            config=payload.config,
            credentials=payload.credentials,
            poll_interval_minutes=payload.poll_interval_minutes,
        )
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return _source_out(source)


@router.get("/kbs/{kb_id}/sources", response_model=list[DataSourceOut])
async def list_sources(
    kb_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[DataSourceOut]:
    """数据源列表(可读者即可见,管理权只在写操作校验)。"""
    kb = await _get_visible_kb(kb_id, db, user)
    return [_source_out(s) for s in await connector_service.list_sources(db, kb.id)]


@router.patch("/kbs/{kb_id}/sources/{source_id}", response_model=DataSourceOut)
async def update_source(
    kb_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: DataSourceUpdate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DataSourceOut:
    """改配置/启停;config 变更整体替换并重新校验。"""
    _kb, source = await _get_source(kb_id, source_id, db, user)
    if payload.name is not None:
        source.name = payload.name.strip() or source.name
    if payload.config is not None:
        try:
            connector_service.validate_config(source.type.value, payload.config)
        except kb_service.KbError as exc:
            raise _http_error(exc) from exc
        source.config = payload.config
    if payload.credentials is not None:
        source.credentials_enc = connector_service._encrypt_credentials(payload.credentials)
    if payload.poll_interval_minutes is not None or "poll_interval_minutes" in payload.model_fields_set:
        source.poll_interval_minutes = payload.poll_interval_minutes
    if payload.status is not None:
        if payload.status not in ("active", "disabled"):
            raise HTTPException(
                status_code=422,
                detail={"code": "validation_error", "message": "status 仅支持 active/disabled"},
            )
        source.status = payload.status
    await db.commit()
    return _source_out(source)


@router.delete("/kbs/{kb_id}/sources/{source_id}", status_code=204)
async def delete_source(
    kb_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    """删除数据源(已同步文档保留为库资产,需求 U8)。"""
    _kb, source = await _get_source(kb_id, source_id, db, user)
    await db.delete(source)
    await db.commit()
    return Response(status_code=204)


@router.post("/kbs/{kb_id}/sources/{source_id}/sync", status_code=202)
async def sync_source(
    kb_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """立即同步(后台执行,轮询 runs 获取结果);正在同步时 400。"""
    _kb, source = await _get_source(kb_id, source_id, db, user)
    try:
        run = await connector_service.trigger_sync(db, source)
    except kb_service.KbError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return {"run_id": str(run.id), "status": run.status.value}


@router.get("/kbs/{kb_id}/sources/{source_id}/runs", response_model=list[SyncRunOut])
async def list_source_runs(
    kb_id: uuid.UUID,
    source_id: uuid.UUID,
    limit: int = 10,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SyncRunOut]:
    """同步运行记录(倒序,默认 10 条)。"""
    _kb, source = await _get_source(kb_id, source_id, db, user)
    return await sync_run_out_list(db, source.id, limit)


async def sync_run_out_list(db: AsyncSession, source_id: uuid.UUID, limit: int) -> list[SyncRunOut]:
    runs = await connector_service.list_runs(db, source_id, limit)
    return [SyncRunOut.model_validate(r) for r in runs]
