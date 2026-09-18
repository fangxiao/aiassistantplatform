"""用户长期记忆:user_memories(M15 P1)

Revision ID: c8e2f5a71d34
Revises: a4d8e6f19b27
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e2f5a71d34"
down_revision: str | Sequence[str] | None = "a4d8e6f19b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_memories_user", "user_memories", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_user_memories_user", table_name="user_memories")
    op.drop_table("user_memories")
