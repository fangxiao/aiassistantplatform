"""内容型连接器:kb_data_sources / kb_sync_runs + kb_documents 连接器溯源列(设计 009)

Revision ID: c2f6b8d94a17
Revises: b7d4e1a92f08
Create Date: 2026-09-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "c2f6b8d94a17"
down_revision: str | Sequence[str] | None = "b7d4e1a92f08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kb_data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kb_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Enum("web", "feishu", "confluence", "github",
                                  name="kb_data_source_type"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("credentials_enc", sa.Text(), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Enum("never", "running", "success", "partial", "failed",
                                         name="kb_sync_status"), nullable=False,
                  server_default="never"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_data_sources_kb_id", "kb_data_sources", ["kb_id"])

    op.create_table(
        "kb_sync_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("never", "running", "success", "partial", "failed",
                                    name="kb_sync_status"), nullable=False,
                  server_default="running"),
        sa.Column("added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_docs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["data_source_id"], ["kb_data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_sync_runs_source_id", "kb_sync_runs", ["data_source_id"])

    op.add_column("kb_documents", sa.Column("data_source_id", sa.Uuid(), nullable=True))
    op.add_column("kb_documents", sa.Column("external_id", sa.Text(), nullable=True))
    op.add_column("kb_documents", sa.Column("external_url", sa.Text(), nullable=True))
    op.create_index(
        "ix_kb_documents_source_doc", "kb_documents", ["data_source_id", "external_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_kb_documents_source_doc", table_name="kb_documents")
    op.drop_column("kb_documents", "external_url")
    op.drop_column("kb_documents", "external_id")
    op.drop_column("kb_documents", "data_source_id")
    op.drop_index("ix_kb_sync_runs_source_id", table_name="kb_sync_runs")
    op.drop_table("kb_sync_runs")
    op.drop_index("ix_kb_data_sources_kb_id", table_name="kb_data_sources")
    op.drop_table("kb_data_sources")
    op.execute("DROP TYPE IF EXISTS kb_data_source_type")
    op.execute("DROP TYPE IF EXISTS kb_sync_status")
