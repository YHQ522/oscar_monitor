"""应用配置 — 基于 pydantic-settings，兼容旧版 data/config.json。"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        # 默认数据目录 = exe 同级 data/（绿色版）
        candidate = Path(os.path.dirname(sys.executable)) / "data"
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_probe"
            probe.touch()
            probe.unlink()
            return candidate
        except OSError:
            # 安装目录不可写（如 Program Files）时回退到用户数据目录，
            # 避免因无写权限导致启动失败
            base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            return base / "oscar_monitor" / "data"
    return Path(__file__).resolve().parent.parent.parent / "data"


class Settings(BaseSettings):
    """全局配置。环境变量前缀 OSCAR_，如 OSCAR_STORAGE_BACKEND=sqlite。"""

    model_config = SettingsConfigDict(env_prefix="OSCAR_", env_file=".env", extra="ignore")

    # ── 基础 ──
    app_name: str = "oscar-monitor"
    data_dir: Path = Field(default_factory=_default_data_dir)
    storage_backend: str = "json"  # json | sqlite
    # 监听端口：优先级 命令行 --port > config.json 的 port > 环境变量 OSCAR_PORT > 5080
    port: int = 5080

    # ── 认证 ──
    # 生产环境请通过环境变量 OSCAR_SECRET_KEY 或 .env 覆盖（≥32 字节）
    secret_key: str = "oscar-monitor-prod-change-me-0123456789abcdef0123456789abcdef"
    token_expire_minutes: int = 1800
    login_max_failures: int = 5
    login_window_seconds: int = 300
    login_ban_duration: int = 900

    # ── 采集 ──
    collect_workers: int = 8
    auto_collect_interval: int = 30
    trend_max_points: int = 288
    # 超时参数（秒）：SSH 连接 / SQL 命令 / OS 检查 / 应用检查 / 启停管控
    ssh_connect_timeout: float = 10.0
    ssh_exec_timeout: int = 120
    os_cmd_timeout: int = 60
    app_cmd_timeout: int = 30
    control_cmd_timeout: int = 120

    # ── 趋势保留 ──
    trend_retention_days: int = 7
    trend_cleanup_interval_hours: int = 24

    # ── 告警通知 ──
    notify_enabled: bool = False
    notify_webhook_url: str = ""
    notify_email_to: str = ""                 # 多个用逗号分隔
    notify_email_from: str = ""
    notify_email_smtp_host: str = ""
    notify_email_smtp_port: int = 465
    notify_email_smtp_user: str = ""
    notify_email_smtp_pass: str = ""
    notify_min_interval: int = 300            # 同一服务器两次通知最小间隔（秒）
    notify_on_health_below: int = 60          # 健康分低于此值触发通知

    # ── 持久化（兼容旧版 config.json 的 log_db 结构）──
    log_enabled: bool = False
    server_db_enabled: bool = False
    log_retention_days: int = 30
    log_db: dict[str, Any] = Field(default_factory=dict)

    # ── 导出 ──
    export_schedule: dict[str, Any] = Field(default_factory=dict)

    # ── 运行时派生 ──
    @property
    def servers_file(self) -> Path:
        return self.data_dir / "servers.json"

    @property
    def users_file(self) -> Path:
        return self.data_dir / "users.json"

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "oscar.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)


def load_legacy_config(data_dir: Path | None = None) -> dict[str, Any]:
    """读取旧版 data/config.json（若存在），用于平滑迁移。"""
    cfg_file = (data_dir or _default_data_dir()) / "config.json"
    if not cfg_file.exists():
        return {}
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _ensure_secret_key(s: Settings) -> None:
    """首次启动生成随机 secret_key 并持久化到 data/secret_key，
    避免使用公开默认密钥导致 JWT 可被伪造。显式配置（环境变量）优先。"""
    default = "oscar-monitor-prod-change-me-0123456789abcdef0123456789abcdef"
    if s.secret_key != default:
        return
    key_file = s.data_dir / "secret_key"
    try:
        if key_file.exists():
            key = key_file.read_text(encoding="utf-8").strip()
            if key:
                s.secret_key = key
                return
        key = secrets.token_hex(32)
        s.data_dir.mkdir(parents=True, exist_ok=True)
        key_file.write_text(key, encoding="utf-8")
        s.secret_key = key
    except OSError:
        logging.getLogger(__name__).warning(
            "无法写入 secret_key 文件，将使用内置默认密钥（生产请设置 OSCAR_SECRET_KEY）"
        )


@lru_cache
def get_settings() -> Settings:
    """获取单例配置。旧版 config.json 中的字段合并覆盖默认值。

    注意：必须覆盖所有 UI 可持久化的键（含通知/超时/趋势保留），
    否则用户保存的配置在重启后回落到默认值。
    """
    s = Settings()
    # 注意：必须用解析后的 s.data_dir（可能被 OSCAR_DATA_DIR 环境变量重定位），
    # 而非 _default_data_dir()，否则安装版/自定义数据目录下会读错 config.json。
    legacy = load_legacy_config(s.data_dir)
    for key in (
        "port",
        "log_enabled",
        "server_db_enabled",
        "log_retention_days",
        "collect_workers",
        "trend_retention_days",
        "ssh_connect_timeout",
        "ssh_exec_timeout",
        "notify_enabled",
        "notify_webhook_url",
        "notify_email_to",
        "notify_email_from",
        "notify_email_smtp_host",
        "notify_email_smtp_port",
        "notify_email_smtp_user",
        "notify_min_interval",
        "notify_on_health_below",
    ):
        if key in legacy:
            setattr(s, key, legacy[key])
    if legacy.get("notify_email_smtp_pass"):
        s.notify_email_smtp_pass = legacy["notify_email_smtp_pass"]
    if legacy.get("log_db"):
        s.log_db = legacy["log_db"]
    if legacy.get("export_schedule"):
        s.export_schedule = legacy["export_schedule"]
    s.ensure_dirs()
    _ensure_secret_key(s)
    return s
