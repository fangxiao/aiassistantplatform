"""会话分享(产品成熟度③):sessions.share_token + expires_at

Revision ID: e8b2d6f43a17
Revises: d6f3a8b21c95
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b2d6f43a17"
down_revision: str | Sequence[str] | None = "d6f3a8b21c95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sessions", sa.Column("share_token", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("share_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_sessions_share_token", "sessions", ["share_token"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sessions_share_token", table_name="sessions")
    op.drop_column("sessions", "share_expires_at")
    op.drop_column("sessions", "share_token")
