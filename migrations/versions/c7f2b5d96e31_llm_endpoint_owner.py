"""LLM 端点归属(用户自定义模型):llm_endpoints.owner_id

Revision ID: c7f2b5d96e31
Revises: b5d9e2c71a40
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7f2b5d96e31"
down_revision: str | Sequence[str] | None = "b5d9e2c71a40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("llm_endpoints", sa.Column("owner_id", sa.Text(), nullable=True))
    op.create_index("ix_llm_endpoints_owner", "llm_endpoints", ["owner_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_llm_endpoints_owner", table_name="llm_endpoints")
    op.drop_column("llm_endpoints", "owner_id")
