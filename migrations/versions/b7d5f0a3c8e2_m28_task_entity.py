"""M28:任务实体化(需求 017/设计 022 §2)

task_entities 表 + 存量定时任务回填(kind=scheduled);手动会话不回填(主动提升)。

Revision ID: b7d5f0a3c8e2
Revises: a9c4e8f1d7b3
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision = "b7d5f0a3c8e2"
down_revision = "a9c4e8f1d7b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_entities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("kind", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("scheduled_task_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_task_entities_user", "task_entities", ["user_id"])
    op.create_index("ix_task_entities_session", "task_entities", ["session_id"], unique=True)
    op.create_index("ix_task_entities_scheduled", "task_entities", ["scheduled_task_id"])
    # 存量回填:全部定时任务 → 实体(需求 017 A5)
    op.execute(
        """
        INSERT INTO task_entities (id, user_id, title, status, kind, scheduled_task_id, created_at)
        SELECT gen_random_uuid(), t.user_id::uuid, t.name,
               CASE WHEN t.enabled THEN 'active' ELSE 'done' END,
               'scheduled', t.id, t.created_at
        FROM scheduled_tasks t
        WHERE NOT EXISTS (
            SELECT 1 FROM task_entities e WHERE e.scheduled_task_id = t.id
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_task_entities_scheduled", table_name="task_entities")
    op.drop_index("ix_task_entities_session", table_name="task_entities")
    op.drop_index("ix_task_entities_user", table_name="task_entities")
    op.drop_table("task_entities")
