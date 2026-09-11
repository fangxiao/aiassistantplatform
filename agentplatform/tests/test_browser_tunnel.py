"""WebSocket 浏览器隧道 API 测试(T11.11)。

使用同步 TestClient(无需 PG),只测隧道握手/心跳/广播:
- 合法 JWT token → 连接 + PING/PONG
- 非法/缺失 token → WebSocketDisconnect(1008)
- 同用户双连接 TAB_UPDATE 广播

隧道端点不依赖 DB,故用最小 app 挂载 /api/browser/tunnel 即可。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentplatform.api.browser import router
from agentplatform.core.auth.service import create_access_token

# 最小 app:只挂浏览器隧道
app = FastAPI()
app.include_router(router, prefix="/api")

client = TestClient(app)


def _valid_token() -> str:
    """签发一个合法测试 JWT(sub 为固定测试用户)。"""
    return create_access_token(subject="test-user-id", role="user")


class TestTunnelAuth:
    def test_valid_token_connects_and_ping_pong(self) -> None:
        token = _valid_token()
        with client.websocket_connect(f"/api/browser/tunnel?token={token}") as ws:
            ws.send_json({"type": "PING"})
            resp = ws.receive_json()
            assert resp == {"type": "PONG"}

    def test_invalid_token_closes_1008(self) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            "/api/browser/tunnel?token=obviously-invalid"
        ):
            pass
        assert exc_info.value.code == 1008

    def test_missing_token_closes_1008(self) -> None:
        with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(
            "/api/browser/tunnel"
        ):
            pass
        assert exc_info.value.code == 1008

    def test_invalid_json_does_not_kill_connection(self) -> None:
        """T11.11:单条非法 JSON 回 ERROR 后连接仍存活,PING/PONG 正常。"""
        token = _valid_token()
        with client.websocket_connect(
            f"/api/browser/tunnel?token={token}&device_id=dev-1"
        ) as ws:
            ws.send_text("{not-json")
            err = ws.receive_json()
            assert err["type"] == "ERROR"
            ws.send_json({"type": "PING"})
            assert ws.receive_json() == {"type": "PONG"}


class TestTunnelTabBroadcast:
    """活跃 Tab 广播:同用户两连接,TAB_UPDATE 从 A 广播到 B。"""

    def test_tab_broadcast_between_same_user(self) -> None:
        token = _valid_token()
        with (
            client.websocket_connect(f"/api/browser/tunnel?token={token}") as ws_a,
            client.websocket_connect(f"/api/browser/tunnel?token={token}") as ws_b,
        ):
            tab = {"title": "测试页", "url": "https://example.com"}
            ws_a.send_json({"type": "TAB_UPDATE", "tab": tab})
            # B 应收到 A 广播的 TAB_UPDATE
            msg = ws_b.receive_json()
            assert msg == {"type": "TAB_UPDATE", "tab": tab}