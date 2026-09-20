"""通知通道 API(产品化):通道 CRUD + 测试发送;任务经 notify.channel_ids 引用。"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.db.session import get_session
from agentplatform.core.notify import service as notify_service
from agentplatform.core.notify.model import NotificationChannel

router = APIRouter(prefix="/notify", tags=["notify"])

CHANNEL_TYPES = ("feishu_webhook", "webhook", "email")


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: str
    config: dict = {}  # {url} 或 {email}
    platform: bool = False  # true=平台级(仅 developer)


class ChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    platform: bool
    enabled: bool
    created_at: datetime


def _out(c: NotificationChannel) -> ChannelOut:
    return ChannelOut(
        id=c.id, name=c.name, type=c.type,
        platform=c.user_id is None, enabled=c.enabled, created_at=c.created_at,
    )


def _validate(cfg_type: str, config: dict) -> None:
    if cfg_type not in CHANNEL_TYPES:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": f"类型须为 {CHANNEL_TYPES}"},
        )
    if cfg_type in ("feishu_webhook", "webhook") and not str(config.get("url") or "").startswith("http"):
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "webhook 通道需要合法 url"})
    if cfg_type == "email" and "@" not in str(config.get("email") or ""):
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "email 通道需要合法邮箱"})


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ChannelOut]:
    """我可用的通道:平台级 ∪ 我的个人通道。"""
    rows = await db.scalars(
        select(NotificationChannel)
        .where(
            NotificationChannel.enabled.is_(True),
            (NotificationChannel.user_id.is_(None)) | (NotificationChannel.user_id == str(user.id)),
        )
        .order_by(NotificationChannel.user_id.is_(None).desc(), NotificationChannel.created_at)
    )
    return [_out(c) for c in rows]


@router.post("/channels", response_model=ChannelOut, status_code=201)
async def create_channel(
    payload: ChannelIn,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ChannelOut:
    """新建通道;platform=true 创建平台级通道(仅 developer)。"""
    _validate(payload.type, payload.config)
    owner = None
    if payload.platform:
        if user.role != UserRole.developer:
            raise HTTPException(
                status_code=403, detail={"code": "forbidden", "message": "平台级通道仅 developer 可创建"}
            )
    else:
        owner = str(user.id)
    row = NotificationChannel(
        user_id=owner, name=payload.name.strip(), type=payload.type,
        config=payload.config, enabled=True,
    )
    db.add(row)
    await db.commit()
    return _out(row)


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await db.get(NotificationChannel, channel_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "通道不存在"})
    is_platform = row.user_id is None
    if is_platform and user.role != UserRole.developer:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "平台级通道仅 developer 可删除"})
    if not is_platform and row.user_id != str(user.id):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "通道不存在"})
    row.enabled = False  # 软删:任务引用不断,发送时跳过
    await db.commit()


@router.post("/channels/{channel_id}/test", status_code=202)
async def test_channel(
    channel_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """发送一条测试消息验证通道连通性。"""
    row = await db.get(NotificationChannel, channel_id)
    if row is None or not row.enabled or (row.user_id and row.user_id != str(user.id)):
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "通道不存在"})
    ok = await notify_service.deliver(row, f"✅ AgentPlatform 通道「{row.name}」测试消息——收到即配置成功")
    return {"ok": ok}
