"""助手独立访问通道(T18.20):开发者运营自有用户的白牌入口。

形态:/a/{access_token} 纯聊天页(无平台 UI),轻注册(昵称即用,自动建号)。
平台 WebUI 保持全员可用(工作台/开发者中心不受影响),本通道是增量分发渠道。
统计:按助手聚合(用户/会话/消息/token),归因经 sessions.plugin_id。
"""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.db.session import get_session
from agentplatform.core.message.model import Message
from agentplatform.core.plugin.model import Plugin
from agentplatform.core.session.model import Session

router = APIRouter(prefix="/assistant-access", tags=["assistant-access"])


async def _plugin_by_token(session: AsyncSession, token: str) -> Plugin:
    plugin = await session.scalar(select(Plugin).where(Plugin.access_token == token))
    if plugin is None or str(plugin.status) != "PluginStatus.active":
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "访问链接无效或助手未发布"})
    return plugin


@router.get("/{token}")
async def access_info(token: str, session: AsyncSession = Depends(get_session)) -> dict:
    """公开:令牌 → 助手展示信息(落地页渲染用,无鉴权)。"""
    plugin = await _plugin_by_token(session, token)
    m = plugin.manifest or {}
    return {
        "plugin_id": str(plugin.id),
        "name": plugin.name,
        "display_name": m.get("display_name") or m.get("title") or plugin.name,
        "description": m.get("description") or "",
    }


class JoinIn(BaseModel):
    nickname: str


@router.post("/{token}/join")
async def join(token: str, payload: JoinIn, session: AsyncSession = Depends(get_session)) -> dict:
    """轻注册:昵称即用——自动建号(无密码)并签发令牌;老用户凭本地凭据复用。"""
    from agentplatform.core.auth.service import create_access_token

    plugin = await _plugin_by_token(session, token)
    nickname = (payload.nickname or "").strip()[:24]
    if not nickname:
        raise HTTPException(status_code=422, detail={"code": "validation_error", "message": "昵称不能为空"})
    email = f"a-{uuid.uuid4().hex[:12]}@assist.local"
    user = await create_user(session, email, secrets.token_urlsafe(24), UserRole.user)
    user.nickname = nickname
    await session.commit()
    return {
        "token": create_access_token(str(user.id), user.role.value),
        "user": {"id": str(user.id), "nickname": nickname},
        "plugin_id": str(plugin.id),
    }


@router.post("/plugins/{plugin_id}/publish")
async def publish_access(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """开发者发布/轮换访问令牌(developer 角色)。"""
    if user.role != UserRole.developer:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "仅开发者可发布"})
    plugin = await session.get(Plugin, plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "插件不存在"})
    token = secrets.token_urlsafe(12)
    plugin.access_token = token
    await session.commit()
    return {"access_token": token, "url": f"/a/{token}"}


@router.get("/plugins/{plugin_id}/stats")
async def assistant_stats(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """按助手使用统计(developer):用户数/会话数/消息数/token 消耗 + 近 14 天消息序列。"""
    if user.role != UserRole.developer:
        raise HTTPException(status_code=403, detail={"code": "forbidden", "message": "仅开发者可查"})
    plugin = await session.get(Plugin, plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "插件不存在"})

    sess_ids = select(Session.id).where(Session.plugin_id == plugin_id)
    users = await session.scalar(
        select(func.count(func.distinct(Session.user_id))).where(Session.plugin_id == plugin_id)
    )
    sessions_n = await session.scalar(
        select(func.count()).select_from(Session).where(Session.plugin_id == plugin_id)
    )
    msgs = await session.scalar(
        select(func.count()).select_from(Message).where(Message.session_id.in_(sess_ids))
    )
    tokens = await session.scalar(
        select(func.coalesce(func.sum(Message.tokens), 0)).where(Message.session_id.in_(sess_ids))
    )
    daily = (
        await session.execute(
            select(
                func.to_char(Message.created_at, "MM-DD").label("day"),
                func.count().label("n"),
            )
            .where(Message.session_id.in_(sess_ids))
            .where(Message.created_at >= func.now() - func.make_interval(0, 0, 0, 14))
            .group_by("day")
            .order_by("day")
        )
    ).all()
    return {
        "users": int(users or 0),
        "sessions": int(sessions_n or 0),
        "messages": int(msgs or 0),
        "tokens": int(tokens or 0),
        "daily": [{"day": d, "messages": int(n)} for d, n in daily],
    }
