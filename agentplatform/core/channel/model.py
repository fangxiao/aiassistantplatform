"""通道会话映射(M22 飞书通道):外部 IM 会话 ↔ 平台 chat 会话。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class ChannelSession(Base):
    """(channel, chat_id) ↔ 平台 session_id 的绑定(设计 012 §2)。

    同一外部会话连续对话复用同一平台会话;/重置 删除绑定,下次消息开新会话。
    """

    __tablename__ = "channel_sessions"
    __table_args__ = (UniqueConstraint("channel", "chat_id", name="uq_channel_chat"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(Text, nullable=False)  # feishu / ...
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)  # 外部会话标识
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
