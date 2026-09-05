"""远程调试会话 API 模型（设计 007 §2）。

创建 / 发送 / 清理 / 心跳四组端点对应的请求与响应模型。
"""

import uuid

from pydantic import BaseModel, Field

from agentplatform.core.plugin.manifest import PluginManifest


class DevSessionCreate(BaseModel):
    """创建调试会话请求：完整 manifest（含各 skill/tool 的 code 源码）。"""

    manifest: PluginManifest


class DevSessionOut(BaseModel):
    """创建成功响应。"""

    ok: bool = True
    session_id: uuid.UUID
    messages_url: str
    ttl_seconds: int
    resources: list[str]


class DevSessionMessageRequest(BaseModel):
    """发送调试消息请求。"""

    content: str = Field(min_length=1, max_length=10000)


class DevSessionMessageOut(BaseModel):
    """心跳/清理响应。"""

    ok: bool = True
    ttl_seconds: int | None = None


class DevSessionHeartbeatRequest(BaseModel):
    """心跳请求（无字段）。"""

