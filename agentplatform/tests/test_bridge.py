"""BrowserBridge 通道路由单元测试(T11.11)。

纯逻辑测试(无 DB / 无 WebSocket),使用假 send 函数验证注册、
路由(route_to_endpoint 返回/超时/未连接)、Tab 广播。
"""

import asyncio
import json

from agentplatform.core.agent.bridge import BrowserBridge

SAMPLE_ACTION = "browser.action.readPage"
SAMPLE_ARGS = {"url": "https://example.com"}


class TestRegistry:
    """register / unregister / is_connected"""

    async def test_register_and_connected(self) -> None:
        bridge = BrowserBridge()
        send_called: list[dict] = []

        async def fake_send(msg: dict) -> None:
            send_called.append(msg)

        sess = bridge.register("user-1", fake_send)
        assert bridge.is_connected("user-1")
        assert sess.user_id == "user-1"
        # 未注册用户
        assert not bridge.is_connected("user-unknown")

    async def test_unregister_disconnects(self) -> None:
        bridge = BrowserBridge()

        async def fake_send(msg: dict) -> None:
            pass

        sess = bridge.register("user-1", fake_send)
        assert bridge.is_connected("user-1")
        bridge.unregister("user-1", sess)
        assert not bridge.is_connected("user-1")

    async def test_multi_session_same_user(self) -> None:
        bridge = BrowserBridge()
        label = {"id": 0}

        async def fake_a(msg: dict) -> None:
            label["id"] = 1

        async def fake_b(msg: dict) -> None:
            label["id"] = 2

        sa = bridge.register("user-1", fake_a)
        sb = bridge.register("user-1", fake_b)
        assert bridge.is_connected("user-1")
        bridge.unregister("user-1", sa)
        assert bridge.is_connected("user-1")  # B 还在
        bridge.unregister("user-1", sb)
        assert not bridge.is_connected("user-1")


class TestRouting:
    """route_to_endpoint / deliver_result"""

    async def test_roundtrip_returns_json_result(self) -> None:
        bridge = BrowserBridge()
        sent: list[dict] = []

        async def fake_send(msg: dict) -> None:
            sent.append(msg)

        bridge.register("user-1", fake_send)

        # 异步地,在 bridge 发 TOOL_CALL 后通过 deliver_result 回传
        call_id = "call_endpoint_1"
        expected = {"rows": [["A", "B"]], "hasHeader": True}

        async def deliver_soon():
            # 让 route_to_endpoint 先完成 send
            await asyncio.sleep(0.01)
            bridge.deliver_result(call_id, expected)

        result_task = asyncio.create_task(deliver_soon())
        result = await bridge.route_to_endpoint(
            "user-1", SAMPLE_ACTION, SAMPLE_ARGS, call_id=call_id, timeout=5
        )
        await result_task

        # 验证 TOOL_CALL 消息格式
        assert len(sent) == 1
        assert sent[0] == {
            "type": "TOOL_CALL",
            "callId": call_id,
            "toolCall": {"name": SAMPLE_ACTION, "args": SAMPLE_ARGS},
        }
        # 验证结果( dict → json.dumps )
        assert json.loads(result) == expected

    async def test_roundtrip_str_result_returned_as_is(self) -> None:
        bridge = BrowserBridge()

        async def fake_send(msg: dict) -> None:
            pass

        bridge.register("user-1", fake_send)
        call_id = "call_str_1"

        async def deliver_soon():
            await asyncio.sleep(0.01)
            bridge.deliver_result(call_id, "plain text result")

        t = asyncio.create_task(deliver_soon())
        result = await bridge.route_to_endpoint(
            "user-1", SAMPLE_ACTION, {}, call_id=call_id, timeout=5
        )
        await t
        assert result == "plain text result"

    async def test_timeout_returns_error_text(self) -> None:
        bridge = BrowserBridge()

        async def fake_send(msg: dict) -> None:
            pass  # 永不响应

        bridge.register("user-1", fake_send)
        result = await bridge.route_to_endpoint(
            "user-1", SAMPLE_ACTION, SAMPLE_ARGS, call_id="call_timeout", timeout=0.1
        )
        assert "超时" in result

    async def test_not_connected_returns_error(self) -> None:
        bridge = BrowserBridge()
        result = await bridge.route_to_endpoint(
            "user-none", SAMPLE_ACTION, SAMPLE_ARGS, call_id="call_nope", timeout=5
        )
        assert "未连接" in result

    async def test_disconnected_during_route(self) -> None:
        bridge = BrowserBridge()

        async def fake_send(msg: dict) -> None:
            pass

        sess = bridge.register("user-1", fake_send)
        call_id = "call_disc"

        async def disconnect_soon():
            await asyncio.sleep(0.01)
            bridge.unregister("user-1", sess)

        t = asyncio.create_task(disconnect_soon())
        result = await bridge.route_to_endpoint(
            "user-1", SAMPLE_ACTION, {}, call_id=call_id, timeout=5
        )
        await t
        assert "中断" in result

    async def test_unknown_call_id_ignored(self) -> None:
        bridge = BrowserBridge()
        bridge.deliver_result("nonexistent", "anything")  # 不应抛异常


class TestTabBroadcast:
    """set_active_tab + TAB_UPDATE 广播"""

    async def test_broadcast_to_other_session(self) -> None:
        bridge = BrowserBridge()
        received_by_b: list[dict] = []

        async def fake_a(msg: dict) -> None:
            pass

        async def fake_b(msg: dict) -> None:
            received_by_b.append(msg)

        sa = bridge.register("user-1", fake_a)
        sb = bridge.register("user-1", fake_b)
        tab = {"title": "Test", "url": "https://example.com"}

        # A 更新 tab → B 应收到 TAB_UPDATE
        bridge.set_active_tab("user-1", sa, tab)
        await asyncio.sleep(0.05)  # 给 _spawn 时间执行

        assert len(received_by_b) == 1
        assert received_by_b[0] == {"type": "TAB_UPDATE", "tab": tab}
        # 发送方会话记录活跃 tab;接收方保留自己的 tab
        assert sa.active_tab == tab
        assert sb.active_tab is None

    async def test_no_broadcast_to_self(self) -> None:
        bridge = BrowserBridge()
        received: list[dict] = []

        async def fake_send(msg: dict) -> None:
            received.append(msg)

        s = bridge.register("user-1", fake_send)
        bridge.set_active_tab("user-1", s, {"title": "X"})
        await asyncio.sleep(0.05)
        # 自己不应收到广播(同会话仅一条)
        assert len(received) == 0