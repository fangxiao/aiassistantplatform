"""M35:官方插件标识(20261012 双层生态)

- plugins.source:official(平台维护,免审批,✓徽标)/ community(默认,开发者)
- 官方插件启动时自动部署/升级(plugins/ 目录)

Revision ID: d5e8b2f7c1a4
Revises: c3f7a1d8e5b2
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "d5e8b2f7c1a4"
down_revision = "e5a9c2f7b4d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plugins",
        sa.Column("source", sa.Text(), nullable=False, server_default="community"),
    )
    # 官方作者(plugins/ 目录下 author 含 "AgentPlatform")回填
    op.execute(
        """
        UPDATE plugins SET source = 'official'
        WHERE manifest->>'author' ILIKE '%AgentPlatform%'
           OR manifest->>'author' ILIKE '%Official%'
        """
    )


def downgrade() -> None:
    op.drop_column("plugins", "source")
