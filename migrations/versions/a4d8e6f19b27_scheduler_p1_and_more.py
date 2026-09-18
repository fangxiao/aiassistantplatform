"""M15 P1 体验完善 + GitHub 连接器预留:scheduled_tasks.target_kb_id / task_runs.alert

Revision ID: a4d8e6f19b27
Revises: f9b3c7e25a01
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4d8e6f19b27"
down_revision: str | Sequence[str] | None = "f9b3c7e25a01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "scheduled_tasks",
        sa.Column("target_kb_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "task_runs",
        sa.Column("alert", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("task_runs", "alert")
    op.drop_column("scheduled_tasks", "target_kb_id")
