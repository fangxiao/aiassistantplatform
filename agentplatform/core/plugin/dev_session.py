"""远程调试会话数据模型与管理器（设计 007 §3.2 / §3.3）。

DevSession 为纯内存态会话，不落 PostgreSQL。TTL 超时或主动清理后
完全消失，不影响注册表和存储。

进程内单例 dev_manager 供路由层（api/plugins.py）使用。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

from agentplatform.config import settings
from agentplatform.core.plugin.manifest import PluginManifest

logger = logging.getLogger(__name__)

# 默认每会话最大消息交互次数（TTL 取 settings.dev_session_ttl）
DEFAULT_MAX_INTERACTIONS = 100


@dataclass
class DevSession:
    """调试会话（内存态，不落 PostgreSQL）。"""

    session_id: str
    user_id: str
    manifest: PluginManifest
    resource_ids: list[str]
    storage_dir: Path
    ttl: int = field(default_factory=lambda: settings.dev_session_ttl)
    created_at: float = field(default_factory=monotonic)
    last_active: float = field(default_factory=monotonic)
    interaction_count: int = 0
    history: list[dict] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        return monotonic() - self.last_active > self.ttl

    @property
    def seconds_remaining(self) -> int:
        remain = int(self.ttl - (monotonic() - self.last_active))
        return max(0, remain)

    def touch(self) -> None:
        self.last_active = monotonic()
        self.interaction_count += 1


class DevSessionManager:
    """进程内调试会话注册表（单例内存存储）。

    多 worker 场景需迁移到 Redis（MVP 单 worker 不做）。
    """

    def __init__(self) -> None:
        self._sessions: dict[str, DevSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        user_id: str,
        manifest: PluginManifest,
        resource_ids: list[str],
        storage_dir: Path,
    ) -> DevSession:
        """创建调试会话（线程安全）。"""
        async with self._lock:
            # 检查同一用户是否有活跃会话
            for sess in self._sessions.values():
                if sess.user_id == user_id and not sess.is_expired:
                    raise DevSessionError("已存在活跃调试会话", "too_many_sessions")

            session_id = str(uuid.uuid4())
            sess = DevSession(
                session_id=session_id,
                user_id=user_id,
                manifest=manifest,
                resource_ids=resource_ids,
                storage_dir=storage_dir,
            )
            self._sessions[session_id] = sess
            logger.info("创建调试会话: %s (user=%s, resources=%d)",
                        session_id, user_id, len(resource_ids))
            return sess

    async def get(self, session_id: str) -> DevSession | None:
        """按 session_id 获取会话；已过期返回 None。"""
        sess = self._sessions.get(session_id)
        if sess is None:
            return None
        if sess.is_expired:
            await self._cleanup_one(sess)
            return None
        return sess

    async def touch(self, session_id: str) -> int:
        """刷新会话活跃时间，返回剩余 TTL 秒数。"""
        sess = self._sessions.get(session_id)
        if sess is None or sess.is_expired:
            raise DevSessionError("调试会话不存在或已过期", "session_expired")
        sess.touch()
        return sess.seconds_remaining

    async def delete(self, session_id: str) -> bool:
        """主动删除会话（CLI exit 时调用）。"""
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            return False
        await self._cleanup_one(sess)
        logger.info("删除调试会话: %s", session_id)
        return True

    async def reap_expired(self) -> int:
        """清理全部过期会话，返回清理数量。"""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            sess = self._sessions.pop(sid, None)
            if sess:
                await self._cleanup_one(sess)
        if expired:
            logger.info("已清理 %d 个过期调试会话", len(expired))
        return len(expired)

    async def list_active(self) -> list[DevSession]:
        """返回全部活跃会话（用于管理/监控）。"""
        return [s for s in self._sessions.values() if not s.is_expired]

    async def _cleanup_one(self, sess: DevSession) -> None:
        """清理单个会话的磁盘资源（注册表清理由调用方负责）。"""
        storage = sess.storage_dir
        if storage.exists():
            import shutil

            shutil.rmtree(storage, ignore_errors=True)


class DevSessionError(Exception):
    """调试会话异常。"""

    def __init__(self, message: str, code: str = "dev_session_error") -> None:
        self.code = code
        super().__init__(message)


# 进程内单例
dev_manager = DevSessionManager()