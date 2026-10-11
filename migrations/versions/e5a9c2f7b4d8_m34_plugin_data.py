"""M34:插件数据存储原语(域无关)——错题本等官方插件的数据层。

平台只提供按 插件/用户/集合 隔离的 jsonb 文档存储;集合内字段结构与查询
语义由插件自定义(分层红线见 plugins/README.md)。

Revision ID: e5a9c2f7b4d8
Revises: b2d6e9f4a7c1
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "e5a9c2f7b4d8"
down_revision = "b2d6e9f4a7c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugin_data",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plugin_name", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("collection", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("plugin_name", "user_id", "collection", "doc_id", name="uq_plugin_data_doc"),
    )
    op.create_index("ix_plugin_data_scope", "plugin_data", ["plugin_name", "user_id", "collection"])


def downgrade() -> None:
    op.drop_index("ix_plugin_data_scope", table_name="plugin_data")
    op.drop_table("plugin_data")
