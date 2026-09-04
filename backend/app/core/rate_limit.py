"""登录限速器 — 线程安全的 IP 级失败计数与封禁。"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class LockInfo:
    since: float
    username: str
    count: int


class LoginRateLimiter:
    def __init__(self, max_failures: int = 5, window: int = 300, ban_duration: int = 900):
        self.max_failures = max_failures
        self.window = window
        self.ban_duration = ban_duration
        self._attempts: dict[str, list[float]] = {}
        self._locked: dict[str, LockInfo] = {}
        self._lock = threading.Lock()

    def check(self, ip: str) -> int:
        """返回剩余封禁分钟数；0 表示未封禁。"""
        now = time.time()
        with self._lock:
            info = self._locked.get(ip)
            if info and now - info.since < self.ban_duration:
                return max(1, int((self.ban_duration - (now - info.since)) / 60) + 1)
            if info:
                self._locked.pop(ip, None)
            attempts = [t for t in self._attempts.get(ip, []) if now - t < self.window]
            if len(attempts) >= self.max_failures:
                oldest = min(attempts)
                if now - oldest < self.ban_duration:
                    self._locked[ip] = LockInfo(since=oldest, username="?", count=len(attempts))
                    return max(1, int((self.ban_duration - (now - oldest)) / 60) + 1)
                self._attempts[ip] = []
            self._attempts[ip] = attempts
        return 0

    def record_failure(self, ip: str) -> None:
        with self._lock:
            self._attempts.setdefault(ip, []).append(time.time())
            # 懒清理：条目过多时移除空/过期记录，防止字典无界增长
            if len(self._attempts) > 512:
                now = time.time()
                for k in [k for k, v in self._attempts.items() if not v or now - max(v) >= self.window]:
                    self._attempts.pop(k, None)

    def set_username(self, ip: str, username: str) -> None:
        """记录封禁条目关联的用户名（仅用于展示）。"""
        with self._lock:
            info = self._locked.get(ip)
            if info:
                info.username = username or "?"

    def clear(self, ip: str) -> None:
        with self._lock:
            self._attempts.pop(ip, None)
            self._locked.pop(ip, None)

    def locked_list(self) -> list[dict]:
        """返回当前封禁 IP 列表（供管理接口展示）。"""
        now = time.time()
        result: list[dict] = []
        with self._lock:
            for ip, info in list(self._locked.items()):
                if now - info.since < self.ban_duration:
                    result.append({
                        "ip": ip,
                        "username": info.username,
                        "count": info.count,
                        "since": time.strftime("%H:%M:%S", time.localtime(info.since)),
                        "remaining_min": max(0, int((self.ban_duration - (now - info.since)) / 60)),
                    })
                else:
                    self._locked.pop(ip, None)
        return result

    def unlock(self, ip: str) -> bool:
        with self._lock:
            existed = ip in self._attempts or ip in self._locked
            self._attempts.pop(ip, None)
            self._locked.pop(ip, None)
        return existed


_login_limiter: LoginRateLimiter | None = None


def get_login_limiter(max_failures: int = 5, window: int = 300, ban_duration: int = 900) -> LoginRateLimiter:
    global _login_limiter
    if _login_limiter is None:
        _login_limiter = LoginRateLimiter(max_failures, window, ban_duration)
    return _login_limiter
