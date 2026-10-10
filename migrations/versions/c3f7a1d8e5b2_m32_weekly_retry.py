"""M32:每周调度 + 失败自动重试(用户对标反馈 20261010)

- scheduled_tasks.weekly_day:weekly 调度的星期(1-7,周一到周日;时刻复用 daily_at)
- task_runs.attempt:执行尝试次数(失败自动重试 1 次,attempt 记录)

Revision ID: c3f7a1d8e5b2
Revises: c8e2b6f4a9d1
Create Date: 2026-10-10
"""
import sqlalchemy as sa
from alembic import op

revision = "c3f7a1d8e5b2"
down_revision = "c8e2b6f4a9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("weekly_day", sa.Integer(), nullable=True))
    op.add_column("task_runs", sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("task_runs", "attempt")
    op.drop_column("scheduled_tasks", "weekly_day")
