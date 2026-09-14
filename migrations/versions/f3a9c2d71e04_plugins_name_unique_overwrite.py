"""助手去版本化:plugins 按 name 全局唯一,同名重部署原地覆盖(ADR 0007)

存量数据收敛:
- plugins 按 name 留最新部署行(其余删除);
- sessions.plugin_id 旧版本行重映射到保留行(无 DB 外键,安全);
- 删除被移除插件的全部私有 skill_tools;删除保留插件的旧版本私有资源;
- drop uq_plugins_name_version,add unique(name)。

Revision ID: f3a9c2d71e04
Revises: e5a8b1c3d726
Create Date: 2026-09-11

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a9c2d71e04"
down_revision: str | Sequence[str] | None = "e5a8b1c3d726"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema + 存量数据收敛。"""
    # 1. 每个 name 保留 deployed_at 最新的一行(并列时任意保留一行)
    op.execute(
        """
        CREATE TEMP TABLE _plugin_keep ON COMMIT DROP AS
        SELECT id, name, version FROM (
            SELECT id, name, version,
                   ROW_NUMBER() OVER (PARTITION BY name ORDER BY deployed_at DESC) AS rn
            FROM plugins
        ) t
        WHERE rn = 1
        """
    )

    # 2. 历史会话从旧版本行重映射到保留行(行 UUID 稳定后会话不再悬挂)
    op.execute(
        """
        UPDATE sessions SET plugin_id = keep.id
        FROM _plugin_keep keep
        JOIN plugins old ON old.name = keep.name AND old.id <> keep.id
        WHERE sessions.plugin_id = old.id
        """
    )

    # 3a. 被移除插件:其名下全部私有注册表资源删除
    op.execute(
        """
        DELETE FROM skill_tools
        WHERE source = 'private'
          AND owner_id IS NOT NULL
          AND owner_id NOT IN (SELECT name FROM _plugin_keep)
        """
    )
    # 3b. 保留插件:旧版本(与保留行 version 不符)的私有资源删除
    op.execute(
        """
        DELETE FROM skill_tools
        WHERE source = 'private'
          AND owner_id IN (SELECT name FROM _plugin_keep)
          AND (owner_id, version) NOT IN (SELECT name, version FROM _plugin_keep)
        """
    )

    # 4. 删除旧版本插件行
    op.execute("DELETE FROM plugins WHERE id NOT IN (SELECT id FROM _plugin_keep)")

    # 5. 唯一约束切换为 name 单列
    op.drop_constraint("uq_plugins_name_version", "plugins", type_="unique")
    op.create_unique_constraint("uq_plugins_name", "plugins", ["name"])


def downgrade() -> None:
    """Downgrade schema(历史版本数据无法恢复,仅恢复约束形态)。"""
    op.drop_constraint("uq_plugins_name", "plugins", type_="unique")
    op.create_unique_constraint(
        "uq_plugins_name_version", "plugins", ["name", "version"]
    )
