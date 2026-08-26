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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agentplatform.config import settings
from agentplatform.core.agent.bridge import BrowserSession, bridge
from agentplatform.core.auth.service import decode_access_token

router = APIRouter(prefix="/browser", tags=["browser"])


def _authenticate(token: str) -> str | None:
    """校验隧道令牌(?token=JWT),返回 user_id;无效/缺失返回 None。"""
    if not token:
        return None
    try:
        claims = decode_access_token(token)
    except Exception:  # noqa: BLE001  认证失败统一按未授权处理
        return None
    return claims.get("sub")


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
        bridge.deliver_result(msg.get("callId"), msg.get("result"))
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
    sess = bridge.register(user_id, send=websocket.send_json)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(), timeout=settings.browser_tunnel_heartbeat
                )
            except TimeoutError:
                # 心跳探测:发 PING,再等一个窗口;仍无消息则判定对端失联
                try:
                    await websocket.send_json({"type": "PING"})
                    await asyncio.wait_for(
                        websocket.receive_json(), timeout=settings.browser_tunnel_timeout
                    )
                except TimeoutError:
                    await websocket.close(code=1001)
                    return
                continue
            await _route_message(websocket, sess, user_id, msg)
    except WebSocketDisconnect:
        pass
    finally:
        bridge.unregister(user_id, sess)
