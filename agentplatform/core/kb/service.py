"""知识库服务(设计 008 §3.3 / 需求 005 §F1、F6)。

库 CRUD、可见性判定、文档增删(hash 去重)、配额校验。
角色说明(001 §2.1:MVP 管理员由开发者兼任):public 建库/发布要求 developer 角色。
"""

import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.kb.model import (
    KbChunk,
    KbDocument,
    KbDocumentStatus,
    KbMember,
    KbVisibility,
    KnowledgeBase,
)

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")  # 注册表 id 组成部分,与 tool:<name> 同风格
ALLOWED_MIME = {"md": "text/markdown", "txt": "text/plain", "pdf": "application/pdf"}
# 文本直存(设计 008 §11):from-text 接口的合法 mime,html 由 pipeline 去标签
ALLOWED_TEXT_MIME = {"text/markdown", "text/plain", "text/html"}


class KbError(Exception):
    """知识库业务错误(message 面向 API 转化)。"""


def kb_storage_dir(kb_id: uuid.UUID, doc_id: uuid.UUID) -> Path:
    """原始文档存储路径(~/.agentplatform/kb/<kb>/<doc>);MVP 本地存储。"""
    return Path.home() / ".agentplatform" / "kb" / str(kb_id) / str(doc_id)


def is_owner(kb: KnowledgeBase, user_id: str | None) -> bool:
    return user_id is not None and str(kb.owner_id) == str(user_id)


async def is_member(db: AsyncSession, kb_id: uuid.UUID, user_id: str | None) -> bool:
    """shared 库成员判定(设计 008 §12);owner 不入库,由 is_owner 另判。"""
    if user_id is None:
        return False
    row = await db.scalar(
        select(KbMember).where(KbMember.kb_id == kb_id, KbMember.user_id == str(user_id))
    )
    return row is not None


async def can_read(db: AsyncSession, kb: KnowledgeBase, user_id: str | None) -> bool:
    """读权限:public 全员;shared owner+成员;private 仅 owner(需求 005 §F6 / 008 §12.2)。"""
    if kb.visibility == KbVisibility.public:
        return kb.status == "active"
    if kb.visibility == KbVisibility.shared:
        return is_owner(kb, user_id) or await is_member(db, kb.id, user_id)
    return is_owner(kb, user_id)


async def can_write(db: AsyncSession, kb: KnowledgeBase, user: User) -> bool:
    """写权限(文档增删):private 仅 owner;shared owner+成员;public 仅 developer(008 §12.2)。"""
    if kb.visibility == KbVisibility.private:
        return is_owner(kb, str(user.id))
    if kb.visibility == KbVisibility.shared:
        return is_owner(kb, str(user.id)) or await is_member(db, kb.id, str(user.id))
    return user.role == UserRole.developer


def can_manage(kb: KnowledgeBase, user: User) -> bool:
    """管理权限(改名/成员管理/删库):private/shared 仅 owner;public developer(§12.2)。"""
    if kb.visibility == KbVisibility.public:
        return user.role == UserRole.developer
    return is_owner(kb, str(user.id))


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


async def list_visible_kbs(db: AsyncSession, user_id: str) -> list[KnowledgeBase]:
    """当前用户可见库:public(active)+ 自己的 private + 自己为 owner/成员的 shared(008 §12.2)。"""
    # 注意:不能用 ORM 实体 select 的 union——union 后 scalars() 只取首列(仅 id)。
    member_kb_ids = select(KbMember.kb_id).where(KbMember.user_id == str(user_id))
    rows = await db.scalars(
        select(KnowledgeBase)
        .where(
            or_(
                and_(
                    KnowledgeBase.visibility == KbVisibility.public,
                    KnowledgeBase.status == "active",
                ),
                and_(
                    KnowledgeBase.visibility == KbVisibility.private,
                    KnowledgeBase.owner_id == str(user_id),
                ),
                and_(
                    KnowledgeBase.visibility == KbVisibility.shared,
                    or_(
                        KnowledgeBase.owner_id == str(user_id),
                        KnowledgeBase.id.in_(member_kb_ids),
                    ),
                ),
            )
        )
        .order_by(KnowledgeBase.updated_at.desc())
    )
    return list(rows)


async def update_kb(
    db: AsyncSession, kb: KnowledgeBase, user: User, *, name: str | None = None,
    description: str | None = None,
) -> KnowledgeBase:
    """改名/描述;管理权限校验(§12.2:管理操作 private/shared 仅 owner)。"""
    if not can_manage(kb, user):
        raise KbError("无权修改该知识库")
    if name is not None:
        kb.name = name
    if description is not None:
        kb.description = description
    await db.flush()
    return kb


async def delete_kb(db: AsyncSession, kb: KnowledgeBase, user: User) -> None:
    """删除库(级联软删文档与物理删片段;public 下架优先走 publish/status)。"""
    if not can_manage(kb, user):
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
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_MIME:
        raise KbError(f"不支持的文档类型: {ext!r}(支持 {sorted(ALLOWED_MIME)})")
    return await _create_document(
        db, kb, user,
        filename=filename,
        mime=ALLOWED_MIME[ext],
        content=content,
        origin="upload",
    )


async def add_document_from_text(
    db: AsyncSession,
    kb: KnowledgeBase,
    user: User,
    *,
    title: str,
    content: str,
    mime: str = "text/markdown",
    source: dict | None = None,
) -> KbDocument:
    """文本直存(设计 008 §11):会话产出物物化为标准文档,复用既有校验与 pipeline。

    source = {app, session_id?, message_id?} 消费无关溯源;(kb_id, source_message_id)
    重复收藏拒绝(幂等;软删文档也计入,避免同消息反复重建)。
    """
    if mime not in ALLOWED_TEXT_MIME:
        raise KbError(f"不支持的文本类型: {mime!r}(支持 {sorted(ALLOWED_TEXT_MIME)})")
    if not content.strip():
        raise KbError("内容为空,无法收藏")
    src = source or {}
    message_id = src.get("message_id")
    if message_id:
        dup_msg = await db.scalar(
            select(KbDocument).where(
                KbDocument.kb_id == kb.id,
                KbDocument.source_message_id == str(message_id),
            )
        )
        if dup_msg is not None:
            raise KbError(f"该消息已收藏至本知识库(文档 {dup_msg.filename})")
    suffix = {"text/markdown": ".md", "text/plain": ".txt", "text/html": ".html"}[mime]
    return await _create_document(
        db, kb, user,
        filename=f"{title.strip() or '未命名'}{suffix}",
        mime=mime,
        content=content.encode("utf-8"),
        origin="session",
        source_app=src.get("app"),
        source_session_id=src.get("session_id"),
        source_message_id=message_id,
    )


async def _create_document(
    db: AsyncSession,
    kb: KnowledgeBase,
    user: User,
    *,
    filename: str,
    mime: str,
    content: bytes,
    origin: str,
    source_app: str | None = None,
    source_session_id: str | None = None,
    source_message_id: str | None = None,
) -> KbDocument:
    """共用落库链(设计 008 §3.3/§11.2):can_write → 大小 → 数量 → hash 去重 → 落盘。"""
    if not await can_write(db, kb, user):
        raise KbError("无权向该知识库写入文档")
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
        mime=mime,
        size_bytes=len(content),
        content_hash=content_hash,
        uploaded_by=str(user.id),
        origin=origin,
        source_app=source_app,
        source_session_id=source_session_id,
        source_message_id=source_message_id,
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
    if not await can_write(db, kb, user):
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


# ---------------------------------------------------------------- 成员管理(设计 008 §12)


async def list_members(db: AsyncSession, kb_id: uuid.UUID) -> list[KbMember]:
    """成员列表(owner 不入库,不在此列)。"""
    rows = await db.scalars(
        select(KbMember).where(KbMember.kb_id == kb_id).order_by(KbMember.created_at)
    )
    return list(rows)


async def add_member(db: AsyncSession, kb: KnowledgeBase, user: User, *, member: User) -> KbMember:
    """添加成员(仅 owner);重复加入拒绝。"""
    if not can_manage(kb, user):
        raise KbError("仅库所有者可管理成员")
    if str(member.id) == str(kb.owner_id):
        raise KbError("该用户已是库所有者")
    existing = await db.scalar(
        select(KbMember).where(KbMember.kb_id == kb.id, KbMember.user_id == str(member.id))
    )
    if existing is not None:
        raise KbError("该用户已是成员")
    row = KbMember(kb_id=kb.id, user_id=str(member.id))
    db.add(row)
    await db.flush()
    return row


async def remove_member(
    db: AsyncSession, kb: KnowledgeBase, user: User, *, member_user_id: str
) -> None:
    """移除成员(仅 owner)。"""
    if not can_manage(kb, user):
        raise KbError("仅库所有者可管理成员")
    row = await db.scalar(
        select(KbMember).where(KbMember.kb_id == kb.id, KbMember.user_id == str(member_user_id))
    )
    if row is None:
        raise KbError("该用户不是成员")
    await db.delete(row)
    await db.flush()
