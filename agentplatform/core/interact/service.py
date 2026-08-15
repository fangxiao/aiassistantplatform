"""交互服务(设计 003 v2.0 §9 / 004 §interact_events)。

处理 WebUI 提交的交互操作与轻反馈事件,记录审计日志并分发到对应 handler。
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.interact.errors import InteractError
from agentplatform.core.interact.model import InteractEvent, InteractKind
from agentplatform.core.message.service import save_assistant_message


async def handle_interaction(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    block_id: str,
    action: str,
    args: dict[str, Any] | None = None,
    value: Any = None,
) -> list[dict[str, Any]]:
    """处理用户在 ContentBlock 上的交互提交。

    1. 记录 interact_events 审计表
    2. 执行 action 逻辑 (内置/插件分发)
    3. 若产生续接 blocks,保存落库并返回给前端
    """
    if not action:
        raise InteractError("action 不能为空", code="invalid_action", status_code=400)

    # 1. 记录审计事件
    event = InteractEvent(
        session_id=session_id,
        block_id=block_id,
        kind=InteractKind.interact,
        action=action,
        value={"args": args, "value": value} if args is not None else value,
    )
    session.add(event)

    # 2. Action 分发处理
    # 对于通用确认/表单提交等动作生成响应 ContentBlock
    response_blocks: list[dict[str, Any]] = []

    if action.endswith("confirm") or action == "input.confirm":
        confirmed = bool(value.get("confirmed") if isinstance(value, dict) else value)
        status_text = "已确认操作" if confirmed else "已取消操作"
        response_blocks.append({
            "type": "markdown",
            "data": {"text": f"✅ **{status_text}**"},
        })
    elif action.endswith("form_submit") or action == "input.form":
        response_blocks.append({
            "type": "markdown",
            "data": {"text": "✅ **表单数据已接收并提交处理。**"},
        })
    else:
        # 通用 fallback 响应
        response_blocks.append({
            "type": "markdown",
            "data": {"text": f"已接收交互指令: `{action}`"},
        })

    # 3. 若有返回 block,持久化一条 assistant 消息
    if response_blocks:
        await save_assistant_message(session, session_id, response_blocks)

    await session.commit()
    return response_blocks


async def record_event(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    kind_str: str,
    block_id: str | None = None,
    value: Any = None,
) -> None:
    """记录轻反馈事件(如 thumbs, regenerate)。"""
    try:
        kind = InteractKind(kind_str)
    except ValueError:
        kind = InteractKind.interact

    event = InteractEvent(
        session_id=session_id,
        block_id=block_id or "global",
        kind=kind,
        action=None,
        value=value,
    )
    session.add(event)
    await session.commit()
