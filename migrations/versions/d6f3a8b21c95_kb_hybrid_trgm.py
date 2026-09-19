"""混合检索地基:pg_trgm 扩展 + kb_chunks(text) trgm 索引

Revision ID: d6f3a8b21c95
Revises: b1e9c3d75f28
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6f3a8b21c95"
down_revision: str | Sequence[str] | None = "b1e9c3d75f28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # pg_trgm 为 PG contrib 自带(pgvector 镜像可用),支持中文 trigram 相似度
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_text_trgm ON kb_chunks USING gin (text gin_trgm_ops)")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_text_trgm")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
