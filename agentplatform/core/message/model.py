"""消息 ORM 模型(设计 004 §messages / 003 v2.0 §3 消息信封)。

blocks 为 ContentBlock 列表(新消息统一用此字段);content 仅历史兼容,
新消息不写(见 003 v2.0 §3.4)。tool_calls / tool_call_id 供 agent 内部回填。
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class MessageRole(str, Enum):
    """消息角色。"""

    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class Message(Base):
    """会话中的一条消息(信封:blocks 存 ContentBlock 列表)。"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, name="message_role"), nullable=False
    )
    blocks: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    content: Mapped[dict | None] = mapped_column(  # 历史兼容,新消息不写
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    tool_calls: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    tool_call_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
