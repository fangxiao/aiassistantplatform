"""轮次追踪(需求 011 H4 / ADR 0010):消息级运行轨迹与错误归因。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class AgentRoundTrace(Base):
    """一条消息轮次的运行记录:token 用量、错误分类(可观测性统一落点)。

    kind: chat(消息轮)/ skill / tool / compaction(H3 P3 扩展)
    error_kind: 空=成功;有值=ErrorKind(六分类)
    """

    __tablename__ = "agent_round_trace"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="chat")
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
