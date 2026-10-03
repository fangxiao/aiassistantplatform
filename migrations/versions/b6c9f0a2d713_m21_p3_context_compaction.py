"""M21 P3:上下文压缩 + 工具调用分流(需求 011 H3/H5,ADR 0011)

- message_role 枚举加 'summary'(滚动摘要行,注入历史不渲染气泡)
- llm_endpoints.supports_native_tools(默认 true;false 才走文本兜底解析)

Revision ID: b6c9f0a2d713
Revises: a5b7e1c8d402
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision = "b6c9f0a2d713"
down_revision = "a5b7e1c8d402"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG 枚举追加值(12+ 支持事务内;防重复用 IF NOT EXISTS)
    op.execute("ALTER TYPE message_role ADD VALUE IF NOT EXISTS 'summary'")
    op.add_column(
        "llm_endpoints",
        sa.Column(
            "supports_native_tools",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("llm_endpoints", "supports_native_tools")
    # 枚举值移除需重建类型,降级从略(summary 行先删除)
    op.execute("DELETE FROM messages WHERE role = 'summary'")
