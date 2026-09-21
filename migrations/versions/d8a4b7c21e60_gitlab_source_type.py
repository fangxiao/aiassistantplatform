"""GitLab 数据源类型:kb_data_source_type 枚举加 'gitlab'

Revision ID: d8a4b7c21e60
Revises: c7f2b5d96e31
Create Date: 2026-09-21

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8a4b7c21e60"
down_revision: str | Sequence[str] | None = "c7f2b5d96e31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema(ADD VALUE 不可回滚,值集一次到位)。"""
    op.execute("ALTER TYPE kb_data_source_type ADD VALUE IF NOT EXISTS 'gitlab'")


def downgrade() -> None:
    """Downgrade: 枚举值不可删除,无操作。"""
