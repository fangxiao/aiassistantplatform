"""M27:组织上下文包标记(需求 016/设计 021 §2)

knowledge_bases.is_context_pack——共享库 + 此标记 = 组织上下文包;
不建新表,检索/成员/挂载链路全部沿用既有 KB 基建。

Revision ID: a9c4e8f1d7b3
Revises: f5b8d2e7c4a9
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "a9c4e8f1d7b3"
down_revision = "f5b8d2e7c4a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_bases",
        sa.Column("is_context_pack", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("knowledge_bases", "is_context_pack")
