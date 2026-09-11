"""浏览器接入网关(RFC-2026-001 RFC-2 / 任务 T11.11)。

`/api/browser/tunnel` WebSocket 隧道:长连接承载端侧浏览器(Chrome 扩展),
提供 身份认证(?token=JWT)、心跳保活、活跃 Tab 广播;并把 agent 的端侧
工具调用经 core/agent/bridge.py 下发(TOOL_CALL)与回收(TOOL_RESULT)。

Wire 协议(JSON,camelCase,遵循 RFC 契约):
  服务端 → 浏览器: TOOL_CALL {type,callId,toolCall{name,args}} / PING / TAB_UPDATE{tab}
  浏览器 → 服务端: TOOL_RESULT {type,callId,result} / PONG / PING / TAB_UPDATE{tab}
"""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from agentplatform.config import settings
from agentplatform.core.agent.bridge import BrowserSession, bridge
from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.auth.service import decode_access_token

router = APIRouter(prefix="/browser", tags=["browser"])


@router.get("/sessions")
async def list_browser_sessions(user: User = Depends(get_current_user)) -> dict:
    """当前用户的浏览器扩展连接自省(设备/活跃 Tab/空闲秒数),供前端排障。"""
    return {"connected": bridge.is_connected(str(user.id)),
            "connections": bridge.sessions_info(str(user.id))}


def _authenticate(token: str) -> str | None:
    """校验隧道令牌(?token=JWT),返回 user_id;无效/缺失返回 None。

    dev 短令牌照样接受与过期 token 宽容提取仅在显式开启 browser_dev_route_any
    的本地联调环境生效;生产默认只接受合法 JWT(旧逻辑以 secret_key 默认值推断,
    生产漏配密钥即放开认证,属安全隐患)。
    """
    if not token:
        return None
    if settings.browser_dev_route_any and token in (
        "dev",
        "dev_token",
        "default_user",
        "local",
        "anonymous",
    ):
        return "default_user"
    try:
        claims = decode_access_token(token)
        return claims.get("sub")
    except Exception:  # noqa: BLE001
        # 本地联调: token 仅过期但结构有效时宽容提取 sub,避免断开本地浏览器
        if settings.browser_dev_route_any:
            try:
                from jose import jwt
                unverified = jwt.get_unverified_claims(token)
                return unverified.get("sub")
            except Exception:
                return None
        return None


async def _route_message(
    websocket: WebSocket, sess: BrowserSession, user_id: str, msg: dict[str, Any]
) -> None:
    """分发浏览器上行消息。"""
    kind = msg.get("type")
    if kind == "PING":
        await websocket.send_json({"type": "PONG"})
    elif kind == "PONG":
        bridge.touch(sess)
    elif kind == "TAB_UPDATE":
        bridge.set_active_tab(user_id, sess, msg.get("tab"))
    elif kind == "TOOL_RESULT":
        # 带 user_id 校验归属,拒绝跨用户伪造他人在途动作的结果
        accepted = bridge.deliver_result(
            msg.get("callId"), msg.get("result"), user_id=user_id
        )
        if not accepted:
            await websocket.send_json(
                {"type": "ERROR", "message": f"未知或无权回传的 callId: {msg.get('callId')}"}
            )
    elif kind in ("STEP_UPDATE", "TOOL_PROGRESS", "PROGRESS"):
        bridge.deliver_step_update(
            msg.get("callId"),
            msg.get("progress") or msg.get("step") or msg.get("data") or msg,
            user_id=user_id,
        )
    # 其余消息忽略(未知协议,留待后续版本)


@router.websocket("/tunnel")
async def browser_tunnel(websocket: WebSocket) -> None:
    """浏览器扩展长连接隧道。"""
    user_id = _authenticate(websocket.query_params.get("token", ""))
    if user_id is None:
        # WebSocket 不走 HTTP 异常处理器,认证失败直接关闭(1008 = policy violation)
        await websocket.close(code=1008)
        return

    await websocket.accept()
    device_id = websocket.query_params.get("device_id") or websocket.query_params.get("deviceId")
    sess = bridge.register(user_id, send=websocket.send_json, device_id=device_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=settings.browser_tunnel_heartbeat
                )
            except TimeoutError:
                # 静默窗口到期:主动 PING 探活;下一窗口内收到的任何消息都照常分发
                # (旧实现直接 continue 会把 PONG/TOOL_RESULT 丢弃,导致路由假性超时)
                await websocket.send_json({"type": "PING"})
                try:
                    msg = await asyncio.wait_for(
                        websocket.receive_json(), timeout=settings.browser_tunnel_timeout
                    )
                except TimeoutError:
                    await websocket.close(code=1001)
                    return
            except WebSocketDisconnect:
                raise
            except Exception:  # noqa: BLE001  单条非法 JSON 不杀连接
                await websocket.send_json({"type": "ERROR", "message": "invalid json message"})
                continue
            await _route_message(websocket, sess, user_id, msg)
    except WebSocketDisconnect:
        pass
    finally:
        bridge.unregister(user_id, sess)
