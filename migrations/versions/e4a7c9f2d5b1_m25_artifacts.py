"""M25:交付物登记表(需求 014/设计 019 §2)

agent 产出(html_render/image_gen)与定时任务报告的统一登记;
存相对 path,展示时现签 URL(签名有 TTL,不落库)。

Revision ID: e4a7c9f2d5b1
Revises: d8f3a1c6b9e2
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "e4a7c9f2d5b1"
down_revision = "d8f3a1c6b9e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("task_run_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_artifacts_user", "artifacts", ["user_id"])
    op.create_index("ix_artifacts_session", "artifacts", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_session", table_name="artifacts")
    op.drop_index("ix_artifacts_user", table_name="artifacts")
    op.drop_table("artifacts")
