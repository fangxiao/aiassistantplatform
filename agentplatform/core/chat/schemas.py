"""对话 API 模型(设计 005 §4)。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateSession(BaseModel):
    plugin_id: uuid.UUID | None = None
    mounted_kb_ids: list[uuid.UUID] = []  # 会话挂载知识库(M12,设计 008 §4.2)


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plugin_id: uuid.UUID | None = None
    title: str | None = None
    mounted_kb_ids: list[uuid.UUID] = []
    created_at: datetime
    updated_at: datetime


class UpdateSession(BaseModel):
    title: str | None = None
    mounted_kb_ids: list[uuid.UUID] | None = None  # None=不修改;[] =清空挂载


class SendMessage(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    text: str
    blocks: list[dict] | None = None
    created_at: datetime

