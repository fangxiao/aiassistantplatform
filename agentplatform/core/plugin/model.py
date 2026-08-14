"""插件 ORM 模型(设计 004 §plugins)。

manifest 存完整插件清单(jsonb);插件即助手(001):model 字段在 manifest 内。
owner_id 暂为 text,M1 引入 users 表后改 FK。
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class PluginStatus(str, Enum):
    """插件启停状态。"""

    active = "active"
    disabled = "disabled"


class Plugin(Base):
    """已部署插件(即可用助手)。"""

    __tablename__ = "plugins"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_plugins_name_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    manifest: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    status: Mapped[PluginStatus] = mapped_column(
        SAEnum(PluginStatus, name="plugin_status"),
        nullable=False,
        default=PluginStatus.active,
    )
    owner_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
