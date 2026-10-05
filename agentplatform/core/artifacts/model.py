"""交付物模型(M25/需求 014/设计 019 §2)。

agent 产出的可打开成果登记:html_render / image_gen 工具产物 + 定时任务报告。
存相对 path(展示时现签 URL——签名有 TTL,落库即过期);report 类凭双引用跳会话。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class Artifact(Base):
    """交付物登记行;登记失败不影响工具原返回(闭环自愈,设计 019 §3)。"""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    task_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # kind: html(image_gen 同为文件类)细分 image / html / report(定时任务产出)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # uploads 下相对路径;report 类为空(凭 task_run_id/session_id 跳转)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
