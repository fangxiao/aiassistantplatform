"""LLM 端点 API 模型(设计 005 §7)。

api_key 仅入站接收明文(创建/更新时),响应中永不返回明文。
"""

import uuid

from pydantic import BaseModel, ConfigDict


class LlmEndpointCreate(BaseModel):
    name: str
    base_url: str
    model: str
    api_key: str
    is_default: bool = False


class LlmEndpointUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    is_default: bool | None = None


class LlmEndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    base_url: str
    model: str
    is_default: bool
