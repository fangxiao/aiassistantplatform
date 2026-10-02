"""通道管理 API(M22 P2-4):飞书机器人凭证 CRUD + 热启停。

绑定模式说明(20261001 用户需求):
- 模式 A(已实现):管理员在此登记已有自建应用的 App ID/Secret,可配 allowlist;
- 模式 B(自动创建):飞书开放平台不提供"创建自建应用"的 API——自建应用只能
  在开放平台控制台手工创建,CLI/接口均无法绕过,故不做。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import require_admin
from agentplatform.core.auth.model import User
from agentplatform.core.channel import feishu as feishu_channel
from agentplatform.core.channel.model import FeishuBot
from agentplatform.core.db.session import get_session as get_db_session
from agentplatform.core.llm.crypto import encrypt

router = APIRouter(prefix="/channel", tags=["channel"])


class BotIn(BaseModel):
    name: str
    app_id: str
    app_secret: str
    allowed_plugins: list[str] | None = None
    enabled: bool = True


def _out(r: FeishuBot) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "app_id": r.app_id,
        "allowed_plugins": r.allowed_plugins,
        "enabled": r.enabled,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/feishu/bots")
async def list_bots(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> list[dict]:
    rows = (await session.scalars(select(FeishuBot).order_by(FeishuBot.created_at))).all()
    return [_out(r) for r in rows]


@router.post("/feishu/bots", status_code=201)
async def create_bot(
    payload: BotIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> dict:
    exists = await session.scalar(select(FeishuBot).where(FeishuBot.app_id == payload.app_id))
    if exists is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "exists", "message": f"app_id 已存在: {payload.app_id}"},
        )
    row = FeishuBot(
        name=payload.name,
        app_id=payload.app_id,
        app_secret_enc=encrypt(payload.app_secret),
        allowed_plugins=payload.allowed_plugins or None,
        enabled=payload.enabled,
    )
    session.add(row)
    await session.commit()
    if row.enabled:
        feishu_channel.start_bot_now(
            {
                "app_id": row.app_id,
                "app_secret": payload.app_secret,
                "allowed": row.allowed_plugins,
                "name": row.name,
            }
        )
    return _out(row)


@router.patch("/feishu/bots/{bot_id}")
async def update_bot(
    bot_id: uuid.UUID,
    payload: BotIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> dict:
    row = await session.get(FeishuBot, bot_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "机器人不存在"})
    row.name = payload.name
    row.allowed_plugins = payload.allowed_plugins or None
    row.enabled = payload.enabled
    if payload.app_secret.strip():
        row.app_secret_enc = encrypt(payload.app_secret)
    await session.commit()
    # 热重载:启用即(重)启,禁用即停
    if row.enabled:
        from agentplatform.core.llm.crypto import decrypt as _dec

        feishu_channel.start_bot_now(
            {
                "app_id": row.app_id,
                "app_secret": _dec(row.app_secret_enc),
                "allowed": row.allowed_plugins,
                "name": row.name,
            }
        )
    else:
        # DB 行仍在(enabled=False):以 DB 状态为准,不触发自愈恢复
        feishu_channel.stop_bot_now(row.app_id, db_row_exists=True)
    return _out(row)


@router.delete("/feishu/bots/{bot_id}")
async def delete_bot(
    bot_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(require_admin),
) -> dict:
    row = await session.get(FeishuBot, bot_id)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "机器人不存在"})
    app_id = row.app_id
    await session.delete(row)
    await session.commit()
    # DB 行已删:若与 settings 同 app_id 则允许自愈恢复默认网关
    feishu_channel.stop_bot_now(app_id, db_row_exists=False)
    return {"ok": True}
