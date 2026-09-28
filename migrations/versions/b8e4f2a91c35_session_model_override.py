"""session model_override:会话级模型动态切换(T18.19)

Revision ID: b8e4f2a91c35
Revises: f3a9c2d71e04
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "b8e4f2a91c35"
down_revision = "f3a9c2d71e04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("model_override", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "model_override")
