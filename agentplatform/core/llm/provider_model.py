"""模型供应商(M29/需求 018/设计 023 §1)。

供应商是端点的组织层:一个 Key + base_url 管一组模型;路由
(resolve_endpoint 按 owner+model 匹配)不感知供应商,风险隔离。
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class LlmProvider(Base):
    """用户自定义模型供应商(OpenAI 兼容);Key Fernet 加密,不回显。"""

    __tablename__ = "llm_providers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)  # 展示名
    preset: Mapped[str] = mapped_column(Text, nullable=False, default="custom")
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # verified=验证通过 / unverified=未通过(可保存,内网/非标上游) / invalid=曾通过后失效
    status: Mapped[str] = mapped_column(Text, nullable=False, default="unverified")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
