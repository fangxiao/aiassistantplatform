"""登录/注册限频(M24/需求 013 A5):进程内滑窗,单实例足够(trial)。"""

import time
from collections import defaultdict, deque

_hits: dict[str, deque] = defaultdict(deque)
_fail: dict[str, list] = []  # placeholder 下方用 dict


def _slide(key: str, limit: int, window_s: float) -> bool:
    """记录一次并判断是否放行;进程重启即清零(可接受)。"""
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def allow_ip_auth(ip: str) -> bool:
    """登录/注册共用:IP 5 次/分钟。"""
    return _slide(f"ip:{ip}", 5, 60.0)


def allow_ip_register(ip: str) -> bool:
    """注册:IP 3 个/小时。"""
    return _slide(f"reg:{ip}", 3, 3600.0)


_account_lock: dict[str, tuple[int, float]] = {}


def account_locked(email: str) -> bool:
    info = _account_lock.get(email)
    return bool(info and time.monotonic() < info[1])


def record_login_fail(email: str) -> None:
    """连续失败 5 次锁 15 分钟;成功登录由 clear 重置。"""
    info = _account_lock.get(email)
    now = time.monotonic()
    count = (info[0] + 1) if info and now < info[1] else 1
    _account_lock[email] = (count, now + 900) if count >= 5 else (count, now + 900)


def clear_login_fail(email: str) -> None:
    _account_lock.pop(email, None)
