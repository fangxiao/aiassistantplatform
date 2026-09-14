"""工作台待办云端化:workbench_todos 表(M14 AI 联动,设计 010)

Revision ID: e1c7f4b93a62
Revises: c2f6b8d94a17
Create Date: 2026-09-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c7f4b93a62"
down_revision: str | Sequence[str] | None = "c2f6b8d94a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "workbench_todos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("origin", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workbench_todos_user", "workbench_todos", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_workbench_todos_user", table_name="workbench_todos")
    op.drop_table("workbench_todos")
