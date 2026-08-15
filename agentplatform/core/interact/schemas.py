"""交互请求与响应 Schema(设计 003 v2.0 §9 / 005 §4)。"""

from typing import Any

from pydantic import BaseModel, Field


class InteractRequest(BaseModel):
    """交互回传请求。"""

    action: str = Field(..., description="调用的 action 名称,如 plugin_id.action_name")
    args: dict[str, Any] | None = Field(default=None, description="固定参数覆盖")
    value: Any = Field(default=None, description="用户提交的值")


class InteractResponse(BaseModel):
    """交互回传响应:返回追加的 ContentBlock 列表。"""

    blocks: list[dict[str, Any]] = Field(default_factory=list, description="续接的 ContentBlock 列表")


class EventRequest(BaseModel):
    """副作用轻反馈事件请求(如 thumbs)。"""

    kind: str = Field(..., description="事件类型,如 thumbs")
    target_block_id: str | None = Field(default=None, description="目标 ContentBlock ID")
    value: Any = Field(default=None, description="操作值,如 1/-1/true")


class EventResponse(BaseModel):
    """事件确认响应。"""

    ok: bool = True
