"""kb shared 可见性与成员管理(M12 增补,设计 008 §12)

kb_visibility 枚举加 'shared'(ADD VALUE 不可回滚,值集一次到位);
新增 kb_members 表(owner 不入库,以 knowledge_bases.owner_id 为准)。

Revision ID: e5a8b1c3d726
Revises: d9e2c4a7f513
Create Date: 2026-09-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5a8b1c3d726"
down_revision: str | Sequence[str] | None = "d9e2c4a7f513"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # PG12+ 事务内 ADD VALUE 前提:新值不在同一事务被使用(本迁移无插入)
    op.execute("ALTER TYPE kb_visibility ADD VALUE IF NOT EXISTS 'shared'")

    op.create_table(
        "kb_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kb_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="member"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["kb_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kb_id", "user_id", name="uq_kb_members_kb_user"),
    )
    op.create_index("ix_kb_members_kb_id", "kb_members", ["kb_id"])
    op.create_index("ix_kb_members_user_id", "kb_members", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_kb_members_user_id", table_name="kb_members")
    op.drop_index("ix_kb_members_kb_id", table_name="kb_members")
    op.drop_table("kb_members")
    # 注:kb_visibility 的 'shared' 值不可移除(ALTER TYPE 无 REMOVE VALUE),降级保留
