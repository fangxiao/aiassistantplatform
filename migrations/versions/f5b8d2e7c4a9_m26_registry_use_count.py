"""M26:注册表使用计数(需求 015/设计 020 §1)

skill_tools.use_count——loop 执行层埋点原子自增;热度榜单与徽标数据源。
存量从 0 起算(不回填)。

Revision ID: f5b8d2e7c4a9
Revises: e4a7c9f2d5b1
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "f5b8d2e7c4a9"
down_revision = "e4a7c9f2d5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "skill_tools",
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("skill_tools", "use_count")
