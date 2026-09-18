"""打磨五项:messages.tokens / task_runs.tokens 成本可观测

Revision ID: b1e9c3d75f28
Revises: c8e2f5a71d34
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1e9c3d75f28"
down_revision: str | Sequence[str] | None = "c8e2f5a71d34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("messages", sa.Column("tokens", sa.Integer(), nullable=True))
    op.add_column("task_runs", sa.Column("tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("task_runs", "tokens")
    op.drop_column("messages", "tokens")
