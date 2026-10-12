"""学习活动追踪模型(M36 学生工作台)。

每次学习行为(答题/背词/练习)记录一行,支撑:
- 学习进度卡(streak/各科统计/今日完成度)
- 家长日报(聚合推送)
- 考试模式(高频错题分析)
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class StudyActivity(Base):
    """一次学习行为(背了 N 个词 / 答了 M 道题 / 纠正了 K 个错)。"""

    __tablename__ = "study_activities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # 行为类型:vocabulary / quiz / mistake_review / photo_upload / practice
    activity_type: Mapped[str] = mapped_column(Text, nullable=False)
    # 科目:chinese / english / math / other
    subject: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    # 数量(词数/题数)
    count: Mapped[int] = mapped_column(nullable=False, default=1)
    # 正确数(答题场景)
    correct: Mapped[int | None] = mapped_column(nullable=True)
    # 来源:scheduled_task / chat / feishu
    source: Mapped[str] = mapped_column(Text, nullable=False, default="chat")
    # 关联会话(可选,溯源)
    session_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
