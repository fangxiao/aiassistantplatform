"""M37:用户角色画像(persona,多选,控制工作台卡片显隐)

users.personas: JSONB 数组 ["student","parent"] —— 空数组/NULL = general(通用)
卡片显示 = 所有人物的并集

Revision ID: f8d0b4e6c3a9
Revises: e6c9d3a5f2b8
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "f8d0b4e6c3a9"
down_revision = "e6c9d3a5f2b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("personas", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("users", "personas")
