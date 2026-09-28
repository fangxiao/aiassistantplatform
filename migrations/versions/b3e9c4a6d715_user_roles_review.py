"""用户体系与发布审批(设计 015 / ADR 0008,M20)

- user_role 枚举加 'admin'(层级制 admin ⊃ developer ⊃ user)
- users.disabled_at(禁用账号)
- plugins.review_status / last_review_reason / reviewed_by / reviewed_at(发布审批)
- 存量 active 插件一次性置 approved(平台既有助手由 admin 背书,避免全员不可用)

Revision ID: b3e9c4a6d715
Revises: 85b6a2fdaa2d
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "b3e9c4a6d715"
down_revision = "85b6a2fdaa2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PG12+ 支持 ADD VALUE 于事务内;IF NOT EXISTS 保证幂等
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'admin'")
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("CREATE TYPE plugin_review_status AS ENUM ('pending_review', 'approved', 'rejected')")
    op.add_column(
        "plugins",
        sa.Column(
            "review_status",
            sa.Enum("pending_review", "approved", "rejected", name="plugin_review_status"),
            nullable=False,
            server_default="pending_review",
        ),
    )
    op.add_column("plugins", sa.Column("last_review_reason", sa.Text(), nullable=True))
    op.add_column("plugins", sa.Column("reviewed_by", sa.Text(), nullable=True))
    op.add_column("plugins", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    # 存量 active 插件背书为已过审(015 §2)
    op.execute("UPDATE plugins SET review_status = 'approved' WHERE status = 'active'")


def downgrade() -> None:
    op.drop_column("plugins", "reviewed_at")
    op.drop_column("plugins", "reviewed_by")
    op.drop_column("plugins", "last_review_reason")
    op.drop_column("plugins", "review_status")
    op.execute("DROP TYPE IF EXISTS plugin_review_status")
    op.drop_column("users", "disabled_at")
    # user_role 的 'admin' 枚举值无法安全移除(PG 不支持 DROP VALUE),保留无害
