"""用户 ORM 模型(设计 004 §users)。

password_hash 存 bcrypt 哈希,明文不落库;role 为用户/开发者。
"""

import uuid
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class UserRole(str, Enum):
    """用户角色。"""

    user = "user"
    developer = "developer"


class User(Base):
    """平台用户。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.user,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )