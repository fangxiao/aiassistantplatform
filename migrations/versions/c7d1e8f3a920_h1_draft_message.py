"""H1 断线检查点(设计 016 §2 / ADR 0009,P1)

- messages.is_draft:草稿消息——流式进行中渐进落库的助手消息;
  断线时留存(检查点),resume 续跑后原地 finalize。

Revision ID: c7d1e8f3a920
Revises: b3e9c4a6d715
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d1e8f3a920"
down_revision = "b3e9c4a6d715"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("messages", "is_draft")
