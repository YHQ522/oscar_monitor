"""趋势历史存储 — 线程安全，每个服务器保留最近 N 条指标点。"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

from .health import extract_metrics


class TrendStore:
    def __init__(self, max_points: int = 288):
        self.max_points = max_points
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def record(self, server_id: str, data: dict[str, Any]) -> None:
        point = extract_metrics(data)
        with self._lock:
            history = self._history.setdefault(server_id, [])
            history.append(point)
            if len(history) > self.max_points:
                self._history[server_id] = history[-self.max_points:]

    def get(self, server_id: str, hours: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            history = list(self._history.get(server_id, []))
        if hours:
            max_points = min(hours * 12, self.max_points)
            return history[-max_points:]
        return history

    def clear(self, server_id: str) -> None:
        with self._lock:
            self._history.pop(server_id, None)

    def cleanup(self, retention_days: int) -> int:
        """删除超过保留天数的历史点，返回移除的点数。保留天数 <=0 表示不清理。"""
        if retention_days <= 0:
            return 0
        cutoff = time.time() - retention_days * 86400
        removed = 0
        with self._lock:
            for sid in list(self._history.keys()):
                kept = []
                for p in self._history[sid]:
                    ts = p.get("ts", "")
                    try:
                        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
                    except (ValueError, TypeError):
                        t = cutoff + 1  # 无法解析的时间戳一律保留
                    if t >= cutoff:
                        kept.append(p)
                    else:
                        removed += 1
                if kept:
                    self._history[sid] = kept
                else:
                    self._history.pop(sid, None)
        return removed


_trend_store: TrendStore | None = None


def get_trend_store(max_points: int = 288) -> TrendStore:
    global _trend_store
    if _trend_store is None:
        _trend_store = TrendStore(max_points)
    return _trend_store
