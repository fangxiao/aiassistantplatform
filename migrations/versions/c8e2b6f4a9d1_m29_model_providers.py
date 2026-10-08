"""M29:模型供应商(需求 018/设计 023 §1/§6)

- llm_providers 表 + llm_endpoints.provider_id
- 存量个人端点(owner 非空)每条迁移为「导入的端点」供应商(preset=custom,
  status=verified——既存可用),端点挂靠;平台共享端点不受影响

Revision ID: c8e2b6f4a9d1
Revises: b7d5f0a3c8e2
Create Date: 2026-10-08
"""
import sqlalchemy as sa
from alembic import op

revision = "c8e2b6f4a9d1"
down_revision = "b7d5f0a3c8e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("preset", sa.Text(), nullable=False, server_default="custom"),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_enc", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="unverified"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_llm_providers_user", "llm_providers", ["user_id"])
    op.add_column("llm_endpoints", sa.Column("provider_id", sa.Uuid(), nullable=True))
    op.create_index("ix_llm_endpoints_provider", "llm_endpoints", ["provider_id"])
    # 存量迁移:每条个人端点 → 一个「导入的端点」供应商(幂等:provider_id 已挂的跳过)
    op.execute(
        """
        INSERT INTO llm_providers (id, user_id, name, preset, base_url, api_key_enc, status, created_at)
        SELECT gen_random_uuid(), e.owner_id, '导入的端点 · ' || e.name, 'custom',
               e.base_url, e.api_key_enc, 'verified', now()
        FROM llm_endpoints e
        WHERE e.owner_id IS NOT NULL AND e.provider_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE llm_endpoints e
        SET provider_id = p.id
        FROM llm_providers p
        WHERE p.user_id = e.owner_id
          AND p.name = '导入的端点 · ' || e.name
          AND p.base_url = e.base_url
          AND e.owner_id IS NOT NULL AND e.provider_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_llm_endpoints_provider", table_name="llm_endpoints")
    op.drop_column("llm_endpoints", "provider_id")
    op.drop_index("ix_llm_providers_user", table_name="llm_providers")
    op.drop_table("llm_providers")
