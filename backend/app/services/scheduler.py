"""采集调度器 — APScheduler 定时采集 + 线程池并发 + 趋势记录 + 错误持久化。"""
from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from ..config import Settings
from .cache import CacheStore, get_cache
from .collector import collect_all
from .health import calc_health_score, smooth_score
from .notify import collect_errors, get_notifier
from .persist import LogPersistService, get_log_service
from .server_service import ServerService, get_server_service
from .trend import TrendStore, get_trend_store

logger = logging.getLogger("oscar_monitor.scheduler")


class CollectScheduler:
    def __init__(
        self,
        settings: Settings,
        server_service: ServerService,
        cache: CacheStore,
        trend: TrendStore,
        log_service: LogPersistService,
    ):
        self.settings = settings
        self.server_service = server_service
        self.cache = cache
        self.trend = trend
        self.log_service = log_service
        self._executor: ThreadPoolExecutor | None = None
        self._persist_executor: ThreadPoolExecutor | None = None
        self._scheduler: BackgroundScheduler | None = None
        self._lock = threading.Lock()
        self._running: set[str] = set()
        self._running_lock = threading.Lock()

    # ── 运行中标记（防止同一服务器并发重复采集） ──
    def _is_running(self, server_id: str) -> bool:
        with self._running_lock:
            return server_id in self._running

    def _mark_running(self, server_id: str, running: bool) -> None:
        with self._running_lock:
            if running:
                self._running.add(server_id)
            else:
                self._running.discard(server_id)

    # ── 线程池 ──
    def _collect_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            workers = max(1, min(32, self.settings.collect_workers))
            self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="collect")
        return self._executor

    def _get_persist_executor(self) -> ThreadPoolExecutor:
        if self._persist_executor is None:
            self._persist_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="persist")
        return self._persist_executor

    def reinit(self) -> None:
        """配置变更后重建线程池，并使采集间隔立即生效。"""
        with self._lock:
            if self._executor:
                self._executor.shutdown(wait=False)
            if self._persist_executor:
                self._persist_executor.shutdown(wait=False)
            self._executor = None
            self._persist_executor = None
            if self._scheduler:
                job = self._scheduler.get_job("auto_collect")
                if job:
                    try:
                        job.reschedule(
                            trigger="interval",
                            seconds=max(1, int(self.settings.auto_collect_interval)),
                        )
                        logger.info("采集间隔已更新为 %s 秒", self.settings.auto_collect_interval)
                    except Exception:  # noqa: BLE001
                        logger.exception("采集间隔更新失败")

    # ── 采集 ──
    def collect_one(self, server: dict[str, Any]) -> dict[str, Any]:
        result = collect_all(
            server,
            server.get("enabled_categories"),
            server.get("enabled_os_checks"),
        )
        self.cache.set(server.get("id"), result)
        self._persist_errors(server, result)
        self.trend.record(server.get("id"), result)
        self._maybe_notify(server, result)
        return result

    def _maybe_notify(self, server: dict[str, Any], result: dict[str, Any]) -> None:
        """采集后评估：健康分过低或存在错误时发送告警通知（不影响采集主流程）。"""
        try:
            score, _ = calc_health_score(
                result,
                server.get("enabled_categories"),
                server.get("enabled_os_checks"),
                bool(server.get("skip_db")),
            )
            # 告警评估使用平滑评分，避免单次采集抖动触发误报
            smoothed = smooth_score(server.get("id", ""), score)
            get_notifier().check_and_send(server, result, smoothed, bool(collect_errors(result)))
        except Exception:  # noqa: BLE001
            logger.exception("告警通知处理失败: %s", server.get("name"))

    def collect_one_async(self, server: dict[str, Any]) -> None:
        self._mark_running(server.get("id", ""), True)
        self._collect_executor().submit(self._safe_collect, server)

    def _safe_collect(self, server: dict[str, Any]) -> None:
        try:
            self.collect_one(server)
        except Exception:  # noqa: BLE001
            logger.exception("采集失败: %s", server.get("name"))
        finally:
            self._mark_running(server.get("id", ""), False)

    def collect_partial(self, server: dict[str, Any], categories: list[str], os_checks: list[str]) -> dict[str, Any]:
        result = collect_all(server, categories or [], os_checks or [])
        self.cache.merge(server.get("id"), result)
        self._persist_errors(server, result)
        return result

    # ── 定时任务 ──
    def _auto_job(self) -> None:
        for server in self.server_service.list():
            sid = server.get("id")
            if self.cache.fresh(sid, max_age=30) or self._is_running(sid):
                continue
            try:
                self.collect_one_async(server)
            except Exception:  # noqa: BLE001
                logger.exception("提交采集任务失败: %s", server.get("name"))

    def _cleanup_trends(self) -> None:
        try:
            removed = self.trend.cleanup(self.settings.trend_retention_days)
            if removed:
                logger.info("趋势清理完成，移除 %s 个过期点", removed)
        except Exception:  # noqa: BLE001
            logger.exception("趋势清理失败")

    def start(self) -> None:
        if self._scheduler is not None:
            return
        scheduler = BackgroundScheduler()
        scheduler.add_job(self._auto_job, "interval", seconds=self.settings.auto_collect_interval, id="auto_collect")
        scheduler.add_job(self.log_service.cleanup_old_logs, "interval", hours=24, id="cleanup_logs")
        scheduler.add_job(
            self._cleanup_trends,
            "interval",
            hours=max(1, self.settings.trend_cleanup_interval_hours),
            id="cleanup_trends",
        )
        scheduler.start()
        self._scheduler = scheduler
        logger.info("采集调度器已启动")

    def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        self.reinit()

    # ── 错误持久化 ──
    def _persist_errors(self, server: dict[str, Any], result: dict[str, Any]) -> None:
        if not server.get("persist_enabled"):
            return
        self._get_persist_executor().submit(self._do_persist, server, result)

    def _do_persist(self, server: dict[str, Any], result: dict[str, Any]) -> None:
        server_name = server.get("name") or server.get("ssh_host", "")
        os_info = result.get("os_info", {})
        for ck, cr in os_info.items():
            text = cr.get("output", "")
            if not text:
                continue
            if ck == "os_errors":
                for line in text.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("==="):
                        self.log_service.persist_os_error(server_name, ck, line)
            elif ck == "db_log_errors":
                self._parse_elog_content(server_name, text)

        perf = result.get("db_queries", {}).get("performance", {})
        slow = perf.get("slow_sql", {})
        if slow and slow.get("rows"):
            for row in slow["rows"]:
                if row and len(row) >= 2:
                    try:
                        cost = float(row[0]) if row[0] else 0
                    except (ValueError, TypeError):
                        cost = 0
                    sql = str(row[1] or "")[:800]
                    if cost >= 0.5 and sql:
                        self.log_service.persist_slow_sql(server_name, {"cost": cost, "sql": sql})

        # 死锁数 > 0 时持久化为 deadlock 类型日志（与首页死锁详情弹窗一致）
        dl = perf.get("deadlock_count", {})
        if dl and not dl.get("error") and dl.get("rows"):
            try:
                n = int(dl["rows"][0][0])
                if n > 0:
                    self.log_service.persist_os_error(server_name, "deadlock", f"死锁数: {n}")
            except (ValueError, IndexError, TypeError):
                pass

    def _parse_elog_content(self, server_name: str, text: str) -> None:
        blocks = text.split("===FILE:")
        for block in blocks:
            if not block.strip():
                continue
            lines = block.split("\n")
            filepath = lines[0].replace("===", "").strip() if lines else ""
            content_lines = lines[1:]
            entry: dict[str, Any] = {}
            for line in content_lines:
                line = line.strip()
                if not line:
                    if entry and entry.get("msg"):
                        entry["tool"] = filepath.split("/")[-1][:100] if filepath else ""
                        self.log_service.persist_db_error(server_name, entry)
                        entry = {}
                    continue
                msg_match = re.match(r"^(ERROR|FATAL|WARNING|PANIC)\s*[:\-]?\s*(.+)", line, re.IGNORECASE)
                if msg_match:
                    if entry and entry.get("msg"):
                        entry["tool"] = filepath.split("/")[-1][:100] if filepath else ""
                        self.log_service.persist_db_error(server_name, entry)
                    entry = {"msg": msg_match.group(2)[:500]}
                    continue
                t_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})", line)
                if t_match and not entry.get("time"):
                    entry["time"] = t_match.group(1)
                u_match = re.search(r"(?:user|USER|User)\s*[=:]\s*(\w+)", line)
                if u_match and not entry.get("user"):
                    entry["user"] = u_match.group(1)
                cost_match = re.search(r"(?:duration|cost|elapsed|耗时)\s*[=:]\s*([\d.]+)\s*(ms|s|秒|毫秒)?", line, re.IGNORECASE)
                if cost_match:
                    cost = float(cost_match.group(1))
                    if cost_match.group(2) in ("ms", "毫秒"):
                        cost = cost / 1000
                    entry["cost"] = round(cost, 3)
                sql_match = re.search(r"(?:statement|sql|query|SQL|语句)\s*[=:]\s*(.+)", line, re.IGNORECASE)
                if sql_match and not entry.get("sql"):
                    entry["sql"] = sql_match.group(1)[:800]
                if not entry.get("msg"):
                    entry["msg"] = line[:500]
            if entry and entry.get("msg"):
                entry["tool"] = filepath.split("/")[-1][:100] if filepath else ""
                self.log_service.persist_db_error(server_name, entry)


_scheduler: CollectScheduler | None = None


def get_collect_scheduler(settings: Settings) -> CollectScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CollectScheduler(
            settings,
            get_server_service(settings),
            get_cache(),
            get_trend_store(settings.trend_max_points),
            get_log_service(settings),
        )
    return _scheduler
