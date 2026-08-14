"""LLM 端点 ORM 模型(设计 004 §llm_endpoints)。

api_key_enc 存储加密后的 key(见 crypto.py);明文不落库、不通过 API 返回。
"""

import uuid

from sqlalchemy import Boolean, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class LlmEndpoint(Base):
    """OpenAI 兼容 LLM 端点配置。"""

    __tablename__ = "llm_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
