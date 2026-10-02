"""M21 P2:agent_round_trace 轮次追踪表(需求 011 H4 / ADR 0010)

Revision ID: a5b7e1c8d402
Revises: f4c8d2a9e305
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa

revision = "a5b7e1c8d402"
down_revision = "f4c8d2a9e305"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_round_trace",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False, server_default="chat"),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("error_kind", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_agent_round_trace_session", "agent_round_trace", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_round_trace_session", table_name="agent_round_trace")
    op.drop_table("agent_round_trace")
