"""通知通道(产品化):notification_channels 表

Revision ID: a9c4d7f18b62
Revises: f1a5c8e30b79
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a9c4d7f18b62"
down_revision: str | Sequence[str] | None = "f1a5c8e30b79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notification_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        # 平台级通道为 null(developer 管理,全员可选);个人级为本人 user_id
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        # feishu_webhook / webhook / email
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_channels_user", "notification_channels", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notification_channels_user", table_name="notification_channels")
    op.drop_table("notification_channels")
