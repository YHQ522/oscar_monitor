"""采集缓存存储 — 线程安全的内存缓存。"""
from __future__ import annotations

import threading
import time
from typing import Any


class CacheStore:
    def __init__(self):
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, server_id: str) -> dict[str, Any] | None:
        with self._lock:
            entry = self._cache.get(server_id)
            return entry.get("data") if entry else None

    def get_entry(self, server_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._cache.get(server_id)

    def set(self, server_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._cache[server_id] = {"data": data, "time": time.time()}

    def merge(self, server_id: str, data: dict[str, Any]) -> None:
        """局部采集结果合并进已有缓存。"""
        with self._lock:
            existing = self._cache.get(server_id, {"data": {}, "time": 0})
            edata = existing.get("data", {})
            if "os_info" in data:
                edata["os_info"] = data["os_info"]
            if "db_queries" in data:
                edata["db_queries"] = data["db_queries"]
            if "apps" in data:
                edata["apps"] = data["apps"]
            edata["server"] = data["server"]
            edata["timestamp"] = data["timestamp"]
            self._cache[server_id] = {"data": edata, "time": time.time()}

    def drop(self, server_id: str) -> None:
        with self._lock:
            self._cache.pop(server_id, None)

    def fresh(self, server_id: str, max_age: float = 30.0) -> bool:
        """判断缓存是否在指定时间窗口内。"""
        with self._lock:
            entry = self._cache.get(server_id)
            return bool(entry and time.time() - entry.get("time", 0) < max_age)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """返回全部数据的只读快照（供 SSE 推送）。"""
        with self._lock:
            return {sid: e.get("data", {}) for sid, e in self._cache.items()}


_cache: CacheStore | None = None


def get_cache() -> CacheStore:
    global _cache
    if _cache is None:
        _cache = CacheStore()
    return _cache
