"""merge T18.20 与 GitLab 数据源双头

Revision ID: 85b6a2fdaa2d
Revises: c9d5e3b72f81, d8a4b7c21e60
Create Date: 2026-09-28 15:17:43.936935

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '85b6a2fdaa2d'
down_revision: Union[str, Sequence[str], None] = ('c9d5e3b72f81', 'd8a4b7c21e60')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
