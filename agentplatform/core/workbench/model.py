"""个人工作台 ORM 模型(M14,设计 010;需求 007 U8 v0.2 待办云端化)。

待办从 localStorage 升级为云端表:AI 经 tool:workbench_todo 写入(多方写入
需要一致存储),附带跨设备同步;前端 TodoCard 与工具共用同一权威存储。
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class WorkbenchTodo(Base):
    """用户待办(工作台卡片与 AI 工具共写;按 user_id 隔离)。"""

    __tablename__ = "workbench_todos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 来源:manual(工作台手输)/ ai(助手经工具写入)
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


from sqlalchemy import Index

Index("ix_workbench_todos_user", WorkbenchTodo.user_id)
