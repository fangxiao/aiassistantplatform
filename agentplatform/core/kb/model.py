"""知识库 ORM 模型(设计 008 §3,ADR 0004/0005)。

三表:knowledge_bases(库) / kb_documents(文档) / kb_chunks(pgvector 片段)。
公共库在 skill_tools 登记 kind=kb 行(注册表行只承担依赖解析,内容在本模块三表)。
软删文档以 kb_documents.status=deleted 表达,检索层 join 过滤即时生效。
"""

import uuid
from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.config import settings
from agentplatform.core.db.base import Base


class KbVisibility(str, Enum):
    """库可见性(需求 005 §F6;§12 增补 shared):private 仅 owner;shared owner+成员;public 全员可读。"""

    private = "private"
    shared = "shared"
    public = "public"


class KbDocumentStatus(str, Enum):
    """文档处理状态机(设计 008 §6)。"""

    pending = "pending"
    parsing = "parsing"
    embedding = "embedding"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"  # 软删:检索过滤,行保留


class KbMember(Base):
    """库成员关系(设计 008 §12);owner 不入库,以 knowledge_bases.owner_id 为准。"""

    __tablename__ = "kb_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kb_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="member")  # 预留角色扩展
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (UniqueConstraint("kb_id", "user_id", name="uq_kb_members_kb_user"),)


class KnowledgeBase(Base):
    """知识库(一等资源)。private 库不进注册表;public 库发布时登记 kind=kb。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # kb:<slug> 组成部分
    visibility: Mapped[KbVisibility] = mapped_column(
        SAEnum(KbVisibility, name="kb_visibility"), nullable=False, default=KbVisibility.private
    )
    owner_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(Text, nullable=False, default="0.0.0")  # public 库 semver
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")  # active / disabled
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class KbDocument(Base):
    """库内文档;status 驱动处理 pipeline,失败原因落 error。"""

    __tablename__ = "kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kb_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)  # md / txt / pdf
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[KbDocumentStatus] = mapped_column(
        SAEnum(KbDocumentStatus, name="kb_document_status"),
        nullable=False,
        default=KbDocumentStatus.pending,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)  # 同库去重
    uploaded_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 溯源(设计 008 §11):origin=upload(页面上传)/ session(会话产出);
    # source_* 消费无关,app 为自由字符串,平台不感知具体消费方
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="upload")
    source_app: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)  # 同库幂等键
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KbChunk(Base):
    """检索片段;kb_id 冗余避免检索 join;source_span 为字符偏移(溯源用)。"""

    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False
    )
    kb_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_span: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # {"start": int, "end": int}
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.kb_embedding_dim), nullable=False
    )


Index("ix_kb_chunks_kb_id", KbChunk.kb_id)
Index("ix_kb_chunks_doc_id", KbChunk.document_id)
Index("ix_kb_documents_kb_id", KbDocument.kb_id)
Index("ix_kb_documents_source_message", KbDocument.kb_id, KbDocument.source_message_id)
Index("ix_kb_members_kb_id", KbMember.kb_id)
Index("ix_kb_members_user_id", KbMember.user_id)
Index("ix_knowledge_bases_owner", KnowledgeBase.owner_id)
