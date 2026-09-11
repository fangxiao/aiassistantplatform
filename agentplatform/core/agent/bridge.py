"""端云通道路由(T11.11 / RFC-2026-001 RFC-2)。

下行 emit(TOOL_CALL)→ 端侧浏览器执行 → 上行 await(TOOL_RESULT)。
WebSocket 网关(api/browser.py)是具体承载;agent loop 通过本模块把端侧
工具调用路由到已连接的浏览器会话,并等待结果回填给 LLM。

进程内单例;多 worker 部署时各 worker 注册表相互独立(POC 单 worker 可接受)。
"""

import asyncio
import json
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from agentplatform.config import settings

Send = Callable[[dict], Awaitable[None]]


@dataclass
class BrowserSession:
    """一次浏览器(扩展)WebSocket 连接。"""

    user_id: str
    send: Send
    device_id: str | None = None
    active_tab: dict | None = None
    last_seen: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        """更新活跃时间戳(收到任何消息时调用)。"""
        self.last_seen = time.monotonic()


class BrowserBridge:
    """端侧浏览器连接注册表 + 双向调用路由。

    - `_sessions`:user_id → 连接列表(一个用户可有多个浏览器窗口)。
    - `_pending`:call_id → (user_id, future),agent 等待端侧 TOOL_RESULT。
    """

    _DISCONNECTED = object()  # 连接中断信号(避免与合法 None 结果混淆)

    def __init__(self) -> None:
        self._sessions: dict[str, list[BrowserSession]] = defaultdict(list)
        self._pending: dict[str, tuple[str, asyncio.Future[Any]]] = {}
        self._progress_listeners: dict[str, Callable[[dict], Awaitable[None]]] = {}

    # ------------------------------------------------------------------ 连接管理
    def register(
        self, user_id: str, send: Send, device_id: str | None = None
    ) -> BrowserSession:
        """登记一个浏览器连接,返回会话句柄。device_id 用于多设备配对识别。"""
        sess = BrowserSession(user_id=user_id, send=send, device_id=device_id)
        self._sessions[user_id].append(sess)
        return sess

    def unregister(self, user_id: str, sess: BrowserSession) -> None:
        """移除连接;并立即使该用户所有在途调用失败,避免长时间悬挂。"""
        sessions = self._sessions.get(user_id, [])
        if sess in sessions:
            sessions.remove(sess)
        if not self._sessions.get(user_id):
            self._sessions.pop(user_id, None)
        for call_id, (owner, fut) in list(self._pending.items()):
            if owner == user_id and not fut.done():
                fut.set_result(self._DISCONNECTED)

    def is_connected(self, user_id: str) -> bool:
        """该用户是否至少有一个活跃浏览器连接。"""
        if bool(self._sessions.get(user_id)):
            return True
        if settings.browser_dev_route_any:
            return bool(self._sessions.get("default_user") or self._sessions)
        return False

    def touch(self, sess: BrowserSession) -> None:
        sess.touch()

    def _active_session(self, user_id: str) -> BrowserSession | None:
        """取该用户最近活跃的连接(多窗口时路由到最活跃那个)。"""
        sessions = self._sessions.get(user_id)
        if not sessions and settings.browser_dev_route_any:
            sessions = self._sessions.get("default_user")
            if not sessions and self._sessions:
                # 提取任意第一个在线连接的会话列表
                sessions = next(iter(self._sessions.values()), [])
        if not sessions:
            return None
        return max(sessions, key=lambda s: s.last_seen)

    # ------------------------------------------------------------------ 双向路由
    async def route_to_endpoint(
        self,
        user_id: str,
        action: str,
        args: dict,
        *,
        call_id: str,
        timeout: float | None = None,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ) -> str:
        """下发 TOOL_CALL 到浏览器并等待 TOOL_RESULT,返回可回填 LLM 的字符串。

        - 无活跃连接 → "错误:浏览器未连接"
        - 超时 → "错误:端侧动作执行超时"
        - 连接中断 → "错误:浏览器连接中断"
        - 成功 → result 为 dict 则 JSON 序列化;为 str 则原样返回。
        """
        if timeout is None:
            timeout = settings.browser_route_timeout
        sess = self._active_session(user_id)
        if sess is None:
            return "错误:浏览器未连接,无法执行端侧动作"
        fut: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending[call_id] = (user_id, fut)
        if on_progress:
            self._progress_listeners[call_id] = on_progress
        try:
            await sess.send(
                {
                    "type": "TOOL_CALL",
                    "callId": call_id,
                    "toolCall": {"name": action, "args": args},
                }
            )
            raw = await asyncio.wait_for(fut, timeout=timeout)
        except TimeoutError:
            return "错误:端侧动作执行超时"
        finally:
            self._pending.pop(call_id, None)
            self._progress_listeners.pop(call_id, None)
        if raw is self._DISCONNECTED:
            return "错误:浏览器连接中断"
        if isinstance(raw, str):
            return raw
        return json.dumps(raw, ensure_ascii=False)

    def deliver_step_update(
        self, call_id: str, step_data: Any, *, user_id: str | None = None
    ) -> bool:
        """端侧 STEP_UPDATE / TOOL_PROGRESS 回传:通知进度监听者。

        user_id 给定时校验该在途调用归属(防跨用户伪造进度);返回是否受理。
        """
        entry = self._pending.get(call_id)
        if entry is None:
            return False
        owner, _ = entry
        if user_id is not None and owner != user_id:
            return False
        cb = self._progress_listeners.get(call_id)
        if cb is not None:
            if isinstance(step_data, str):
                step_obj = {"message": step_data}
            elif isinstance(step_data, dict):
                step_obj = step_data
            else:
                step_obj = {"data": step_data}
            _spawn(cb(step_obj))
        return True

    def deliver_result(
        self, call_id: str, result: Any, *, user_id: str | None = None
    ) -> bool:
        """端侧 TOOL_RESULT 回传:解析对应 future。

        未知 call_id 忽略;user_id 给定时校验归属,跨用户回传直接丢弃,
        防止已连接的浏览器伪造他人在途动作的结果。返回是否受理。
        """
        entry = self._pending.get(call_id)
        if entry is None:
            return False
        owner, fut = entry
        if user_id is not None and owner != user_id:
            return False
        if not fut.done():
            fut.set_result(result)
        return True

    def sessions_info(self, user_id: str) -> list[dict[str, Any]]:
        """该用户当前浏览器连接自省(device/活跃 Tab/最近 seen),供排障端点使用。"""
        now = time.monotonic()
        return [
            {
                "device_id": s.device_id,
                "active_tab": s.active_tab,
                "idle_seconds": round(now - s.last_seen, 1),
            }
            for s in self._sessions.get(user_id, ())
        ]

    # ------------------------------------------------------------------ 活跃 Tab
    def set_active_tab(self, user_id: str, sess: BrowserSession, tab: dict | None) -> None:
        """记录活跃 Tab 并广播给该用户的其他连接(多窗口同步)。"""
        sess.active_tab = tab
        sess.touch()
        for other in self._sessions.get(user_id, ()):
            if other is not sess:
                _spawn(self._send_broadcast(other, tab))

    async def _send_broadcast(self, sess: BrowserSession, tab: dict | None) -> None:
        try:
            await sess.send({"type": "TAB_UPDATE", "tab": tab})
        except Exception:  # noqa: BLE001, S110  对端可能已断,由连接循环统一清理
            pass


def _spawn(coro: Awaitable[None]) -> None:
    """fire-and-forget:后台发送广播,吞异常避免未消费警告。"""
    task = asyncio.ensure_future(coro)

    def _done(_: asyncio.Task) -> None:
        if not task.cancelled():
            task.exception()  # 消费异常,防 "Task exception was never retrieved"

    task.add_done_callback(_done)


# 进程内单例
bridge = BrowserBridge()
