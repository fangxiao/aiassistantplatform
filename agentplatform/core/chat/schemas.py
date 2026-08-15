"""对话 API 模型(设计 005 §4)。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateSession(BaseModel):
    plugin_id: uuid.UUID | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plugin_id: uuid.UUID | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime


class UpdateSession(BaseModel):
    title: str


class SendMessage(BaseModel):
    content: str


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    text: str
    blocks: list[dict] | None = None
    created_at: datetime

