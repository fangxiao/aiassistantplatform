"""M36:学生工作台(学习活动追踪 + 家长日报 + 考试模式)

- study_activities 表:每次学习行为(答题/背词/练习)
- scheduled_tasks 新增 kind:parent_report(家长日报)/ exam_prep(考试模式)
- scheduled_tasks 加 exam_date / exam_subjects(考试倒计时)

Revision ID: e6c9d3a5f2b8
Revises: d5e8b2f7c1a4
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "e6c9d3a5f2b8"
down_revision = "d5e8b2f7c1a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_activities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_type", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False, server_default="other"),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("correct", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="chat"),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_study_activities_user", "study_activities", ["user_id"])

    op.add_column("scheduled_tasks", sa.Column("exam_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("scheduled_tasks", sa.Column("exam_subjects", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "exam_subjects")
    op.drop_column("scheduled_tasks", "exam_date")
    op.drop_index("ix_study_activities_user", table_name="study_activities")
    op.drop_table("study_activities")
