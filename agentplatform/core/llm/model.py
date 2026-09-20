"""LLM 端点 ORM 模型(设计 004 §llm_endpoints)。

api_key_enc 存储加密后的 key(见 crypto.py);明文不落库、不通过 API 返回。
endpoint_type(M12,设计 008 §3.2):chat 对话 / embedding 向量化,密钥管理复用。
"""

import uuid
from enum import Enum

from sqlalchemy import Boolean, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class EndpointType(str, Enum):
    """端点用途。"""

    chat = "chat"
    embedding = "embedding"


class LlmEndpoint(Base):
    """OpenAI 兼容 LLM 端点配置。"""

    __tablename__ = "llm_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_enc: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 端点归属(用户自定义模型):null=平台共享端点(developer 管理);
    # user_id=个人端点,仅本人可见可用,密钥自己管
    owner_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_type: Mapped[EndpointType] = mapped_column(
        SAEnum(EndpointType, name="llm_endpoint_type", create_type=False),
        nullable=False,
        default=EndpointType.chat,
        server_default="chat",
    )
