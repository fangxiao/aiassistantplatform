"""交互事件 ORM 模型(设计 004 §interact_events / 003 v2.0 §9)。

记录用户在 ContentBlock 上的交互操作、点赞/点踩轻反馈以及重新生成事件。
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class InteractKind(str, Enum):
    """交互事件类型。"""

    interact = "interact"
    thumbs = "thumbs"
    regenerate = "regenerate"


class InteractEvent(Base):
    """交互事件记录。"""

    __tablename__ = "interact_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_id: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[InteractKind] = mapped_column(
        SAEnum(InteractKind, name="interact_kind"), nullable=False
    )
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
