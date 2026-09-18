"""用户长期记忆 ORM(M15 P1,设计对标豆包类产品的记忆系统)。

agent 经 tool:memory 写入用户偏好/事实;会话组装时注入 system prompt。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class UserMemory(Base):
    """一条用户记忆(内容短文本;按 user_id 隔离;LLM 通过工具增删查)。"""

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 一句话事实/偏好
    # Python 端微秒时间戳:同秒批量插入时保证"新→旧"排序稳定
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )


Index("ix_user_memories_user", UserMemory.user_id)
