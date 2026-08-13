"""init

Revision ID: 11802f9f44aa
Revises: 
Create Date: 2026-08-13 10:18:07.996390

"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = '11802f9f44aa'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
