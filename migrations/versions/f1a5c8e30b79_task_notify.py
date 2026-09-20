"""任务通知出口(成熟度④):scheduled_tasks.notify jsonb

Revision ID: f1a5c8e30b79
Revises: e8b2d6f43a17
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "f1a5c8e30b79"
down_revision: str | Sequence[str] | None = "e8b2d6f43a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "scheduled_tasks",
        sa.Column("notify", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("scheduled_tasks", "notify")
