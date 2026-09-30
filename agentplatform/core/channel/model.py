"""通道会话映射(M22 飞书通道):外部 IM 会话 ↔ 平台 chat 会话。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from sqlalchemy.dialects.postgresql import JSONB

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
    # M22 P2:消息归属的飞书用户(自动开通通道账号;空=旧数据/服务账号)
    feishu_open_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class FeishuBot(Base):
    """多机器人凭证(P2-4):每个飞书自建应用一条;allowlist 限定可用助手。

    secret 以平台 fernet 加密存储(llm/crypto);enabled=False 停用即断开。
    """

    __tablename__ = "feishu_bots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    app_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    app_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # 可用助手插件名列表;null/空 = 不限(全部可用)
    allowed_plugins: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
