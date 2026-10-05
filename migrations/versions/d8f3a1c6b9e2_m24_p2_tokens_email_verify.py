"""M24 P2:双令牌 + 邮箱验证(需求 013 §4 / 设计 018 §5)

- users.email_verified_at:非空即已验证;存量已绑定第三方身份的用户回填 now()
- refresh_tokens:轮换链令牌族(明文仅存 cookie,库存 sha256)

Revision ID: d8f3a1c6b9e2
Revises: c7d2e8f1a430
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "d8f3a1c6b9e2"
down_revision = "c7d2e8f1a430"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("ip", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_refresh_tokens_user", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family", "refresh_tokens", ["family_id"])
    op.create_index("ix_refresh_tokens_hash", "refresh_tokens", ["token_hash"], unique=True)
    # 存量回填:已绑定第三方身份(GitHub 等)视为已验证(设计 018 §5)
    op.execute(
        """
        UPDATE users SET email_verified_at = now()
        WHERE email_verified_at IS NULL
          AND EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id = users.id)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_column("users", "email_verified_at")
