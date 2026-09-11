"""kb_documents 会话产出溯源字段(M12 增补,设计 008 §11)

origin(upload/session)+ source_app/source_session_id/source_message_id;
(kb_id, source_message_id) 唯一性由服务层校验(软删文档会让 DB 级唯一约束误伤重收藏)。

Revision ID: d9e2c4a7f513
Revises: c3f7a91b2d40
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e2c4a7f513"
down_revision: str | Sequence[str] | None = "c3f7a91b2d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "kb_documents",
        sa.Column("origin", sa.Text(), nullable=False, server_default="upload"),
    )
    op.add_column("kb_documents", sa.Column("source_app", sa.Text(), nullable=True))
    op.add_column(
        "kb_documents", sa.Column("source_session_id", sa.Text(), nullable=True)
    )
    op.add_column(
        "kb_documents", sa.Column("source_message_id", sa.Text(), nullable=True)
    )
    op.create_index(
        "ix_kb_documents_source_message", "kb_documents", ["kb_id", "source_message_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_kb_documents_source_message", table_name="kb_documents")
    op.drop_column("kb_documents", "source_message_id")
    op.drop_column("kb_documents", "source_session_id")
    op.drop_column("kb_documents", "source_app")
    op.drop_column("kb_documents", "origin")
