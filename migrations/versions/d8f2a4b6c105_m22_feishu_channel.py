"""M22 飞书通道(需求 012)

- channel_sessions 表:外部 IM 会话(channel, chat_id) ↔ 平台 session_id 绑定。

Revision ID: d8f2a4b6c105
Revises: c7d1e8f3a920
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "d8f2a4b6c105"
down_revision = "c7d1e8f3a920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("chat_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("channel", "chat_id", name="uq_channel_chat"),
    )


def downgrade() -> None:
    op.drop_table("channel_sessions")
