"""user_files 上传留痕 + knowledge_bases.personal_default(20261015 个人知识库)。

- user_files:/files/upload 每次落一行,"我的文件"面板数据源(设计:用户可见
  自己传过的全部附件,并可一键转存知识库)。
- knowledge_bases.personal_default:个人库"随对话自动挂载"标记;partial unique
  index 保证每用户至多一个默认库。授权链经 resolve_allowed_kb_ids 并入(所有者
  的会话全局可检索自己的默认个人库,全局生效、可关)。

Revision ID: a1b2c3d4e5f6
Revises: f8d0b4e6c3a9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f8d0b4e6c3a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False, index=True),
        sa.Column("path", sa.Text(), nullable=False, comment="服务端存储路径"),
        sa.Column("name", sa.Text(), nullable=False, comment="原始文件名"),
        sa.Column("size", sa.Integer(), nullable=False, default=0),
        sa.Column("mime", sa.Text(), nullable=False, default="application/octet-stream"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_files_user_created", "user_files", ["user_id", "created_at"])

    op.add_column(
        "knowledge_bases",
        sa.Column("personal_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # 每用户至多一个默认个人库(partial unique index,PG 专属)
    op.create_index(
        "ux_knowledge_bases_personal_default",
        "knowledge_bases",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("personal_default IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("ux_knowledge_bases_personal_default", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "personal_default")
    op.drop_table("user_files")
