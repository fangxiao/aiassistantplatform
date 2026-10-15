"""用户上传文件留痕(20261015「我的文件」)。

/files/upload 每次成功落一行;面板列全量附件,支持一键转存个人/公共知识库。
历史文件(留痕功能上线前)经回填脚本从消息块补录。
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from agentplatform.core.db.base import Base


class UserFile(Base):
    """一次成功的文件上传。"""

    __tablename__ = "user_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False, comment="服务端存储路径")
    name: Mapped[str] = mapped_column(Text, nullable=False, comment="原始文件名")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mime: Mapped[str] = mapped_column(Text, nullable=False, default="application/octet-stream")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
