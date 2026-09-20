"""动作审计(M17 P1):action_logs 表

Revision ID: b5d9e2c71a40
Revises: a9c4d7f18b62
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d9e2c71a40"
down_revision: str | Sequence[str] | None = "a9c4d7f18b62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "action_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_logs_user", "action_logs", ["user_id"])
    op.create_index("ix_action_logs_created", "action_logs", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_action_logs_created", table_name="action_logs")
    op.drop_index("ix_action_logs_user", table_name="action_logs")
    op.drop_table("action_logs")
