"""add knowledge base tables (M12, 设计 008)

启用 pgvector;knowledge_bases / kb_documents / kb_chunks 三表;
skill_tools.kind 枚举加 'kb'(ADR 0005);llm_endpoints 加 endpoint_type;
sessions 加 mounted_kb_ids。

Revision ID: c3f7a91b2d40
Revises: a8e411bf9812
Create Date: 2026-09-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from agentplatform.config import settings
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "c3f7a91b2d40"
down_revision: str | Sequence[str] | None = "a8e411bf9812"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # pgvector 扩展(ADR 0004);需 pgvector/pgvector 镜像或预装扩展的 PG
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # skill_tool_kind 枚举扩展(ADR 0005);ADD VALUE 不可回滚,值集一次到位。
    # PG12+ 允许事务内 ADD VALUE,前提是新值不在同一事务被使用(本迁移无插入)
    op.execute("ALTER TYPE skill_tool_kind ADD VALUE IF NOT EXISTS 'kb'")

    dim = settings.kb_embedding_dim
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column(
            "visibility",
            sa.Enum("private", "public", name="kb_visibility"),
            nullable=False,
            server_default="private",
        ),
        sa.Column("owner_id", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=False, server_default="0.0.0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_knowledge_bases_owner", "knowledge_bases", ["owner_id"])

    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kb_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "parsing",
                "embedding",
                "ready",
                "failed",
                "deleted",
                name="kb_document_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("uploaded_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_documents_kb_id", "kb_documents", ["kb_id"])

    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("kb_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source_span", JSONB(), nullable=False, server_default="{}"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(dim), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["kb_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_chunks_kb_id", "kb_chunks", ["kb_id"])
    op.create_index("ix_kb_chunks_doc_id", "kb_chunks", ["document_id"])
    # cosine 相似度检索索引(ivfflat 对小规模更省内存;lists 取 sqrt(rows) 量级)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding "
        "ON kb_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # llm_endpoints.endpoint_type(M12:embedding 端点,密钥管理复用)
    op.execute("CREATE TYPE llm_endpoint_type AS ENUM ('chat', 'embedding')")
    op.add_column(
        "llm_endpoints",
        sa.Column(
            "endpoint_type",
            sa.Enum("chat", "embedding", name="llm_endpoint_type", create_type=False),
            nullable=False,
            server_default="chat",
        ),
    )

    # sessions.mounted_kb_ids(M12:会话运行时挂载,设计 008 §4.2)
    op.add_column(
        "sessions",
        sa.Column("mounted_kb_ids", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sessions", "mounted_kb_ids")
    op.drop_column("llm_endpoints", "endpoint_type")
    op.execute("DROP TYPE IF EXISTS llm_endpoint_type")
    op.drop_index("ix_kb_chunks_embedding", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_doc_id", table_name="kb_chunks")
    op.drop_index("ix_kb_chunks_kb_id", table_name="kb_chunks")
    op.drop_table("kb_chunks")
    op.drop_index("ix_kb_documents_kb_id", table_name="kb_documents")
    op.drop_table("kb_documents")
    op.drop_index("ix_knowledge_bases_owner", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
    op.execute("DROP TYPE IF EXISTS kb_document_status")
    op.execute("DROP TYPE IF EXISTS kb_visibility")
    # 注:skill_tool_kind 的 'kb' 值不可移除(ALTER TYPE 无 REMOVE VALUE),降级保留
