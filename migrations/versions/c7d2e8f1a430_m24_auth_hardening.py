"""M24 P1:认证加固(需求 013/设计 018)

- user_identities:第三方身份绑定(GitHub OAuth 等)
- personal_access_tokens:CLI 开发令牌(可撤销,与登录 JWT 解耦)
- invite_codes:邀请码注册制

Revision ID: c7d2e8f1a430
Revises: b6c9f0a2d713
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d2e8f1a430"
down_revision = "b6c9f0a2d713"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_uid", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "provider_uid", name="uq_identity_provider_uid"),
    )
    op.create_index("ix_user_identities_user", "user_identities", ["user_id"])

    op.create_table(
        "personal_access_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pat_user", "personal_access_tokens", ["user_id"])
    op.create_index("uq_pat_hash", "personal_access_tokens", ["token_hash"], unique=True)

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("invite_codes")
    op.drop_index("uq_pat_hash", table_name="personal_access_tokens")
    op.drop_index("ix_pat_user", table_name="personal_access_tokens")
    op.drop_table("personal_access_tokens")
    op.drop_index("ix_user_identities_user", table_name="user_identities")
    op.drop_table("user_identities")
