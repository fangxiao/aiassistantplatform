"""seed builtin skill tool resources

Revision ID: 98efc5a8b1f9
Revises: 9d77390fe3f6
Create Date: 2026-08-13 11:58:25.696603

数据迁移:登记平台内置 skill/tool(设计 002 §3.2,source=builtin)。
元信息单一来源为 agentplatform.core.registry.builtin(与种子脚本/M5 执行器共用)。
用 SQLAlchemy Core 而非 exec_driver_sql,由 SA 处理方言占位符与枚举/jsonb 适配。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from agentplatform.core.registry.builtin import ALL
from agentplatform.core.registry.model import SkillTool
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "98efc5a8b1f9"
down_revision: str | Sequence[str] | None = "9d77390fe3f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """登记全部内置资源(幂等:同 id+version 已存在则跳过)。"""
    conn = op.get_bind()
    for res in ALL:
        exists = conn.execute(
            sa.select(SkillTool.id).where(
                SkillTool.id == res["id"], SkillTool.version == res["version"]
            )
        ).first()
        if exists:
            continue
        conn.execute(
            sa.insert(SkillTool).values(
                id=res["id"],
                version=res["version"],
                kind=res["kind"],
                name=res["name"],
                source="builtin",
                schema=res["schema"],
                impl_path=f"agentplatform.core.registry.builtin.{res['name'].replace('-', '_')}",
                description=res["description"],
            )
        )


def downgrade() -> None:
    """移除内置资源登记。"""
    conn = op.get_bind()
    ids = [res["id"] for res in ALL]
    conn.execute(sa.delete(SkillTool).where(SkillTool.id.in_(ids)))
