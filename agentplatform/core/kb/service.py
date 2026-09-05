"""知识库服务(设计 008 §3.3 / 需求 005 §F1、F6)。

库 CRUD、可见性判定、文档增删(hash 去重)、配额校验。
角色说明(001 §2.1:MVP 管理员由开发者兼任):public 建库/发布要求 developer 角色。
"""

import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import CompoundSelect, Select

from agentplatform.config import settings
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.kb.model import (
    KbChunk,
    KbDocument,
    KbDocumentStatus,
    KbVisibility,
    KnowledgeBase,
)

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")  # 注册表 id 组成部分,与 tool:<name> 同风格
ALLOWED_MIME = {"md": "text/markdown", "txt": "text/plain", "pdf": "application/pdf"}


class KbError(Exception):
    """知识库业务错误(message 面向 API 转化)。"""


def kb_storage_dir(kb_id: uuid.UUID, doc_id: uuid.UUID) -> Path:
    """原始文档存储路径(~/.agentplatform/kb/<kb>/<doc>);MVP 本地存储。"""
    return Path.home() / ".agentplatform" / "kb" / str(kb_id) / str(doc_id)


def can_read(kb: KnowledgeBase, user_id: str | None) -> bool:
    """读权限:public 全员;private 仅 owner(需求 005 §F6.1/F6.2)。"""
    if kb.visibility == KbVisibility.public:
        return kb.status == "active"
    return user_id is not None and str(kb.owner_id) == str(user_id)


def can_write(kb: KnowledgeBase, user: User) -> bool:
    """写权限:private 仅 owner;public 仅 developer 角色(管理员兼任,运营库)。"""
    if kb.visibility == KbVisibility.private:
        return str(kb.owner_id) == str(user.id)
    return user.role == UserRole.developer


async def create_kb(
    db: AsyncSession,
    *,
    name: str,
    slug: str,
    owner: User,
    visibility: KbVisibility = KbVisibility.private,
    description: str | None = None,
) -> KnowledgeBase:
    """新建库;slug 唯一且格式受限(public 要求 developer 角色)。"""
    if not SLUG_RE.match(slug):
        raise KbError(f"slug 不合法(小写字母开头,字母/数字/下划线,2-64 位): {slug!r}")
    if visibility == KbVisibility.public and owner.role != UserRole.developer:
        raise KbError("仅 developer 角色可创建公共知识库")
    existing = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.slug == slug))
    if existing is not None:
        raise KbError(f"slug 已存在: {slug!r}")
    kb = KnowledgeBase(
        name=name,
        slug=slug,
        visibility=visibility,
        owner_id=str(owner.id),
        description=description,
    )
    db.add(kb)
    await db.flush()
    return kb


async def get_kb(db: AsyncSession, kb_id: uuid.UUID) -> KnowledgeBase | None:
    return await db.get(KnowledgeBase, kb_id)


async def list_visible_kbs(
    db: AsyncSession, user_id: str, include_own_private: bool = True
) -> list[KnowledgeBase]:
    """当前用户可见库:public(active)+ 自己的 private。"""
    stmt = select(KnowledgeBase).where(
        KnowledgeBase.visibility == KbVisibility.public,
        KnowledgeBase.status == "active",
    )
    final: Select[tuple[KnowledgeBase]] | CompoundSelect[tuple[KnowledgeBase]] = stmt
    if include_own_private:
        own = select(KnowledgeBase).where(
            KnowledgeBase.visibility == KbVisibility.private,
            KnowledgeBase.owner_id == str(user_id),
        )
        final = stmt.union(own)
    rows = await db.scalars(final.order_by(KnowledgeBase.updated_at.desc()))
    return list(rows)


async def update_kb(
    db: AsyncSession, kb: KnowledgeBase, user: User, *, name: str | None = None,
    description: str | None = None,
) -> KnowledgeBase:
    """改名/描述;写权限校验。"""
    if not can_write(kb, user):
        raise KbError("无权修改该知识库")
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    await db.flush()
    return kb


async def delete_kb(db: AsyncSession, kb: KnowledgeBase, user: User) -> None:
    """删除库(级联软删文档与物理删片段;public 下架优先走 publish/status)。"""
    if not can_write(kb, user):
        raise KbError("无权删除该知识库")
    await db.execute(delete(KbChunk).where(KbChunk.kb_id == kb.id))
    await db.execute(delete(KbDocument).where(KbDocument.kb_id == kb.id))
    await db.delete(kb)
    await db.flush()


async def add_document(
    db: AsyncSession,
    kb: KnowledgeBase,
    user: User,
    *,
    filename: str,
    mime: str,
    content: bytes,
) -> KbDocument:
    """上传文档:类型/大小/数量/hash 去重校验 → 落盘 → pending,等待 pipeline。"""
    if not can_write(kb, user):
        raise KbError("无权向该知识库上传文档")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_MIME:
        raise KbError(f"不支持的文档类型: {ext!r}(支持 {sorted(ALLOWED_MIME)})")
    max_bytes = settings.kb_max_document_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise KbError(f"文档超过大小上限 {settings.kb_max_document_mb}MB")
    doc_count = await db.scalar(
        select(func.count()).select_from(KbDocument).where(
            KbDocument.kb_id == kb.id, KbDocument.status != KbDocumentStatus.deleted
        )
    )
    if (doc_count or 0) >= settings.kb_max_documents_per_kb:
        raise KbError(f"文档数达到单库上限 {settings.kb_max_documents_per_kb}")
    content_hash = hashlib.sha256(content).hexdigest()
    dup = await db.scalar(
        select(KbDocument).where(
            KbDocument.kb_id == kb.id,
            KbDocument.content_hash == content_hash,
            KbDocument.status != KbDocumentStatus.deleted,
        )
    )
    if dup is not None:
        raise KbError(f"内容重复(已存在文档 {dup.filename})")

    doc = KbDocument(
        kb_id=kb.id,
        filename=filename,
        mime=ALLOWED_MIME[ext],
        size_bytes=len(content),
        content_hash=content_hash,
        uploaded_by=str(user.id),
    )
    db.add(doc)
    await db.flush()
    path = kb_storage_dir(kb.id, doc.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    kb.doc_count = (kb.doc_count or 0) + 1
    kb.size_bytes = (kb.size_bytes or 0) + len(content)
    await db.flush()
    return doc


async def soft_delete_document(
    db: AsyncSession, kb: KnowledgeBase, doc: KbDocument, user: User
) -> None:
    """软删文档:检索层 join 过滤即时生效;片段物理删除释放空间。"""
    if not can_write(kb, user):
        raise KbError("无权删除该文档")
    await db.execute(delete(KbChunk).where(KbChunk.document_id == doc.id))
    doc.status = KbDocumentStatus.deleted
    kb.doc_count = max(0, (kb.doc_count or 0) - 1)
    kb.size_bytes = max(0, (kb.size_bytes or 0) - doc.size_bytes)
    kb.chunk_count = await db.scalar(
        select(func.count()).select_from(KbChunk).where(KbChunk.kb_id == kb.id)
    ) or 0
    await db.flush()


async def list_documents(
    db: AsyncSession, kb_id: uuid.UUID, include_deleted: bool = False
) -> list[KbDocument]:
    """文档列表(默认不含已删)。"""
    stmt = select(KbDocument).where(KbDocument.kb_id == kb_id)
    if not include_deleted:
        stmt = stmt.where(KbDocument.status != KbDocumentStatus.deleted)
    rows = await db.scalars(stmt.order_by(KbDocument.created_at.desc()))
    return list(rows)
