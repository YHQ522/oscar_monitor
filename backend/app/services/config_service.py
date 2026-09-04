"""系统配置服务 — 读写 data/config.json 并同步 Settings 单例。"""
from __future__ import annotations

import json
import time
from typing import Any

from ..config import Settings, get_settings


def _read_file(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_file(path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ConfigService:
    _CACHE_TTL = 2.0  # 读缓存 TTL（秒）：避免每次请求都读磁盘；保存后立即失效

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache: tuple[float, dict[str, Any]] | None = None

    def get(self) -> dict[str, Any]:
        """返回配置（log_db / 通知密码脱敏）。带短 TTL 内存缓存，避免频繁读磁盘。"""
        now = time.monotonic()
        if self._cache and now - self._cache[0] < self._CACHE_TTL:
            return self._cache[1]
        cfg = _read_file(self.settings.config_file)
        result = self._build(cfg)
        self._cache = (now, result)
        return result

    def _build(self, cfg: dict[str, Any]) -> dict[str, Any]:
        log_db = cfg.get("log_db", {}) or {}
        return {
            "log_db": {
                **log_db,
                "pass": bool(log_db.get("pass")),  # 脱敏：仅返回是否有密码
                "ssh_pass": bool(log_db.get("ssh_pass")),
            },
            "log_enabled": cfg.get("log_enabled", self.settings.log_enabled),
            "server_db_enabled": cfg.get("server_db_enabled", self.settings.server_db_enabled),
            "log_retention_days": cfg.get("log_retention_days", self.settings.log_retention_days),
            "collect_workers": cfg.get("collect_workers", self.settings.collect_workers),
            "auto_collect_interval": cfg.get("auto_collect_interval", self.settings.auto_collect_interval),
            "port": cfg.get("port", self.settings.port),
            "export_schedule": cfg.get("export_schedule", self.settings.export_schedule),
            "storage_backend": self.settings.storage_backend,
            "trend_retention_days": cfg.get("trend_retention_days", self.settings.trend_retention_days),
            "ssh_connect_timeout": cfg.get("ssh_connect_timeout", self.settings.ssh_connect_timeout),
            "ssh_exec_timeout": cfg.get("ssh_exec_timeout", self.settings.ssh_exec_timeout),
            "notify": {
                "enabled": cfg.get("notify_enabled", self.settings.notify_enabled),
                "webhook_url": cfg.get("notify_webhook_url", ""),
                "email_to": cfg.get("notify_email_to", ""),
                "email_from": cfg.get("notify_email_from", ""),
                "email_smtp_host": cfg.get("notify_email_smtp_host", ""),
                "email_smtp_port": cfg.get("notify_email_smtp_port", self.settings.notify_email_smtp_port),
                "email_smtp_user": cfg.get("notify_email_smtp_user", ""),
                "email_smtp_pass": bool(cfg.get("notify_email_smtp_pass")),  # 脱敏
                "min_interval": cfg.get("notify_min_interval", self.settings.notify_min_interval),
                "on_health_below": cfg.get("notify_on_health_below", self.settings.notify_on_health_below),
            },
        }

    def update(self, data: dict[str, Any]) -> dict[str, Any]:
        cfg = _read_file(self.settings.config_file)
        if "log_db" in data:
            new_db = data["log_db"]
            old_db = cfg.get("log_db", {}) or {}
            # 密码未填写时保留旧值
            if "pass" in new_db and not new_db.get("pass"):
                new_db["pass"] = old_db.get("pass", "")
            if "ssh_pass" in new_db and not new_db.get("ssh_pass"):
                new_db["ssh_pass"] = old_db.get("ssh_pass", "")
            cfg["log_db"] = new_db
        if "notify" in data:
            new_notify = data["notify"] or {}
            old_notify = cfg.get("notify_enabled") is not None
            # 密码未填写时保留旧值
            if "email_smtp_pass" in new_notify and not new_notify.get("email_smtp_pass"):
                new_notify["email_smtp_pass"] = cfg.get("notify_email_smtp_pass", "")
            for key, value in new_notify.items():
                cfg["notify_" + key] = value
            if not old_notify and not new_notify.get("enabled"):
                pass  # 保持默认关闭
        for key in (
            "log_enabled", "server_db_enabled", "log_retention_days", "collect_workers",
            "auto_collect_interval", "export_schedule", "trend_retention_days", "ssh_connect_timeout", "ssh_exec_timeout",
            "port",
        ):
            if key in data:
                cfg[key] = data[key]
        _write_file(self.settings.config_file, cfg)
        self._cache = None  # 保存后立即失效读缓存
        # 同步 Settings 单例
        self._sync_settings(cfg)
        # 通知配置变更后重建通知器，使新配置立即生效
        if "notify" in data:
            from .notify import reinit_notifier

            reinit_notifier(self.settings)
        return self.get()

    def _sync_settings(self, cfg: dict[str, Any]) -> None:
        s = self.settings
        s.log_enabled = bool(cfg.get("log_enabled", s.log_enabled))
        s.server_db_enabled = bool(cfg.get("server_db_enabled", s.server_db_enabled))
        s.log_retention_days = int(cfg.get("log_retention_days", s.log_retention_days))
        s.collect_workers = int(cfg.get("collect_workers", s.collect_workers))
        s.auto_collect_interval = int(cfg.get("auto_collect_interval", s.auto_collect_interval))
        s.port = int(cfg.get("port", s.port))
        s.trend_retention_days = int(cfg.get("trend_retention_days", s.trend_retention_days))
        s.ssh_connect_timeout = float(cfg.get("ssh_connect_timeout", s.ssh_connect_timeout))
        s.ssh_exec_timeout = int(cfg.get("ssh_exec_timeout", s.ssh_exec_timeout))
        s.notify_enabled = bool(cfg.get("notify_enabled", s.notify_enabled))
        s.notify_webhook_url = cfg.get("notify_webhook_url", "")
        s.notify_email_to = cfg.get("notify_email_to", "")
        s.notify_email_from = cfg.get("notify_email_from", "")
        s.notify_email_smtp_host = cfg.get("notify_email_smtp_host", "")
        s.notify_email_smtp_port = int(cfg.get("notify_email_smtp_port", s.notify_email_smtp_port))
        s.notify_email_smtp_user = cfg.get("notify_email_smtp_user", "")
        if cfg.get("notify_email_smtp_pass"):
            s.notify_email_smtp_pass = cfg["notify_email_smtp_pass"]
        s.notify_min_interval = int(cfg.get("notify_min_interval", s.notify_min_interval))
        s.notify_on_health_below = int(cfg.get("notify_on_health_below", s.notify_on_health_below))
        if cfg.get("log_db"):
            s.log_db = cfg["log_db"]
        if cfg.get("export_schedule"):
            s.export_schedule = cfg["export_schedule"]


_config_service: ConfigService | None = None


def get_config_service(settings: Settings | None = None) -> ConfigService:
    global _config_service
    if _config_service is None or settings is not None:
        _config_service = ConfigService(settings or get_settings())
    return _config_service
