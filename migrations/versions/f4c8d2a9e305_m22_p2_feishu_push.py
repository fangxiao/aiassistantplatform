"""M22 P2-3:定时任务结果推送飞书

- scheduled_tasks.feishu_chat_id:任务产出推送的目标飞书会话(空=不推送)

Revision ID: f4c8d2a9e305
Revises: e9a3c5d7b216
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "f4c8d2a9e305"
down_revision = "e9a3c5d7b216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("feishu_chat_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "feishu_chat_id")
