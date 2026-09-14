"""助手挂载知识库:plugins.mounted_kb_ids(设计 008 §4.3,T12.17)

Revision ID: b7d4e1a92f08
Revises: f3a9c2d71e04
Create Date: 2026-09-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "b7d4e1a92f08"
down_revision: str | Sequence[str] | None = "f3a9c2d71e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "plugins",
        sa.Column(
            "mounted_kb_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("plugins", "mounted_kb_ids", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("plugins", "mounted_kb_ids")
