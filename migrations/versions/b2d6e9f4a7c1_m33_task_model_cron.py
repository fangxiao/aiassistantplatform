"""M33:定时任务增强(20261011 词汇/文言文任务复盘)

- scheduled_tasks.model_override:任务级模型选型(空=平台默认/插件 manifest;
  sessions.model_override 同款机制 T18.19——auto 池抽签方差大,内容型任务
  需要能钉住具体模型)
- scheduled_tasks.cron_expr:cron 调度(schedule_type='cron' 时必填,5 段
  标准表达式,服务器本地时区;daily/weekly/interval 覆盖不到"每月1号"等场景)

Revision ID: b2d6e9f4a7c1
Revises: c3f7a1d8e5b2
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "b2d6e9f4a7c1"
down_revision = "c3f7a1d8e5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scheduled_tasks", sa.Column("model_override", sa.Text(), nullable=True))
    op.add_column("scheduled_tasks", sa.Column("cron_expr", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "cron_expr")
    op.drop_column("scheduled_tasks", "model_override")
