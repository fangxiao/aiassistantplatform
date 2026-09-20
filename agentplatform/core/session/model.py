"""会话 ORM 模型(设计 004 §sessions)。

user_id 暂为 text(M1 引入 users 表后改 FK);plugin_id 指向已部署插件(助手)。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class Session(Base):
    """一次对话会话(关联某个插件助手)。"""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)  # M1 后 FK
    plugin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 会话分享(产品成熟度③):非空即开启只读分享;过期后 404
    share_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    share_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 运行时挂载的知识库 id 列表(M12,设计 008 §4.2);服务端写入前校验可读
    mounted_kb_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
