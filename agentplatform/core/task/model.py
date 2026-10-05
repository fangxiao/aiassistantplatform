"""任务实体模型(M28/需求 017/设计 022 §2)。

task 是**组织对象**非执行对象:执行仍走会话(session_id 唯一引用,一对一);
定时任务经 scheduled_task_id 间接绑定。M25 聚合视图保留为「未提升会话」区。
"""

import uuid
from datetime import UTC, datetime

from agentplatform.core.db.base import Base
from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class TaskEntity(Base):
    """任务实体:命名/状态流转/交付物归集(artifacts 按 session_id 天然关联)。"""

    __tablename__ = "task_entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")  # active/done/archived
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="manual")  # manual/scheduled
    # manual 的执行载体(唯一:一会话最多提升为一个任务)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, unique=True, index=True)
    # kind=scheduled 时引用;定时任务删除 → 实体转 done(不级联删)
    scheduled_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
