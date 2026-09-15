"""定时任务 ORM 模型(M15,设计 011;Scheduled Agent Runs)。

scheduled_tasks:用户级定时任务(到点以创建者身份运行一次 agent);
task_runs:运行记录(产出全文/会话追溯)。task 删除保留 runs(审计),
故 task_runs.task_id 不加 FK 约束。
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class ScheduledTask(Base):
    """用户定时任务(调度状态持久化:next_run_at 重启恢复;错过不补跑,顺延)。"""

    __tablename__ = "scheduled_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="briefing")  # briefing/inspection/custom
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")  # custom 必填;模板任务可附补充要求
    schedule_type: Mapped[str] = mapped_column(Text, nullable=False, default="daily")  # daily / interval
    daily_at: Mapped[str | None] = mapped_column(Text, nullable=True)  # "HH:MM"(服务器时区)
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plugin_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # 空=平台通用助手
    mounted_kb_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)  # 空=运行时取可见库
    auto_save_kb: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(Text, nullable=False, default="never")  # never/running/success/failed
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


Index("ix_scheduled_tasks_user", ScheduledTask.user_id)


class TaskRun(Base):
    """任务运行记录;产出全文落 output,会话追溯走 session_id。"""

    __tablename__ = "task_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)  # 无 FK:任务删除保留审计
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")  # running/success/failed
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_task_runs_task_id", TaskRun.task_id)
