"""动作审计日志(M17 P1):tool:http_request 调用留痕,洞察页可视化。"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class ActionLog(Base):
    """一次外部动作调用(执行/拒绝/取消均记录)。"""

    __tablename__ = "action_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # executed(已执行) / pending(挂起等确认) / confirmed(确认后执行)
    # rejected(白名单/SSRF 拒绝) / cancelled(用户取消) / error(请求失败)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
