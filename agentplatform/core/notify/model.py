"""通知通道 ORM(产品化):平台级(全员)与个人级通道,任务按 id 引用。"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class NotificationChannel(Base):
    """通知通道:feishu_webhook / webhook / email。

    user_id 为 null 表示平台级通道(developer 创建,全员可选);
    config 形如 {url} 或 {email},按 type 解释。
    """

    __tablename__ = "notification_channels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


Index("ix_notification_channels_user", NotificationChannel.user_id)
