"""M22 P2:飞书通道按 open_id 独立账号 + 多机器人表

- channel_sessions.feishu_open_id:消息归属的飞书用户
- feishu_bots:多机器人凭证(app_id/secret 加密存储)+ 可用助手 allowlist

Revision ID: e9a3c5d7b216
Revises: d8f2a4b6c105
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "e9a3c5d7b216"
down_revision = "d8f2a4b6c105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "channel_sessions",
        sa.Column("feishu_open_id", sa.Text(), nullable=True),
    )
    op.create_table(
        "feishu_bots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("app_id", sa.Text(), nullable=False, unique=True),
        sa.Column("app_secret_enc", sa.Text(), nullable=False),
        sa.Column("allowed_plugins", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("feishu_bots")
    op.drop_column("channel_sessions", "feishu_open_id")
