"""plugin access_token:助手独立访问链接令牌(T18.20)

Revision ID: c9d5e3b72f81
Revises: b8e4f2a91c35
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d5e3b72f81"
down_revision = "b8e4f2a91c35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plugins", sa.Column("access_token", sa.Text(), nullable=True))
    op.create_index("ix_plugins_access_token", "plugins", ["access_token"], unique=True)
    op.add_column("users", sa.Column("nickname", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_index("ix_plugins_access_token", table_name="plugins")
    op.drop_column("plugins", "access_token")
    op.drop_column("users", "nickname")
