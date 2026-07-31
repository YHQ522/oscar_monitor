"""服务器管理服务 — 依赖 ServerRepository，封装默认值与 CRUD 业务规则。"""
from __future__ import annotations

import time
import uuid
from typing import Any

from ..adapters import get_query_sets
from ..config import Settings
from ..models.server import ServerCreate, ServerUpdate
from ..repositories import ServerRepository


class ServerService:
    def __init__(self, repo: ServerRepository, settings: Settings):
        self.repo = repo
        self.settings = settings

    def list(self) -> list[dict[str, Any]]:
        servers = self.repo.list()
        for s in servers:
            self._apply_defaults(s)
        return servers

    def get(self, server_id: str) -> dict[str, Any] | None:
        s = self.repo.get(server_id)
        if s:
            self._apply_defaults(s)
        return s

    def create(self, data: ServerCreate) -> dict[str, Any]:
        payload = data.model_dump()
        if self.settings.log_enabled is False and payload.get("persist_enabled"):
            raise ValueError("全局日志持久化未启用，请先在系统配置中启用")
        payload["id"] = uuid.uuid4().hex[:8]
        # None = 未提供 → 填充默认；[] = 用户显式选择（如“仅系统”/“仅数据库”），必须尊重
        if payload.get("enabled_categories") is None:
            payload["enabled_categories"] = list(get_query_sets(payload.get("db_type")).keys())
        if payload.get("enabled_os_checks") is None:
            payload["enabled_os_checks"] = ["memory", "disk", "cpu", "install_path", "os_errors", "db_log_errors"]
        payload.setdefault("auto_refresh", 0)
        payload.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        servers = self.repo.list()
        servers.append(payload)
        self.repo.save_all(servers)
        return payload

    def update(self, server_id: str, data: ServerUpdate) -> dict[str, Any] | None:
        server = self.repo.get(server_id)
        if not server:
            return None
        payload = data.model_dump(exclude_unset=True)
        if self.settings.log_enabled is False and payload.get("persist_enabled"):
            raise ValueError("全局日志持久化未启用，请先在系统配置中启用")
        server.update(payload)
        self._apply_defaults(server)
        servers = self.repo.list()
        servers = [s if s.get("id") != server_id else server for s in servers]
        self.repo.save_all(servers)
        return server

    def delete(self, server_id: str) -> bool:
        existed = self.repo.get(server_id) is not None
        if existed:
            self.repo.delete(server_id)
        return existed

    def _apply_defaults(self, s: dict[str, Any]) -> None:
        # 仅对字段缺失或为 None（旧数据）填充默认；空列表表示用户显式选择，必须尊重。
        if "enabled_categories" not in s or s.get("enabled_categories") is None:
            s["enabled_categories"] = list(get_query_sets(s.get("db_type")).keys())
        if "enabled_os_checks" not in s or s.get("enabled_os_checks") is None:
            s["enabled_os_checks"] = ["memory", "disk", "cpu", "install_path", "os_errors", "db_log_errors"]
        if "in_control" not in s:
            s["in_control"] = True
        if "apps" not in s:
            s["apps"] = []
        if "persist_enabled" not in s:
            s["persist_enabled"] = False
        if "db_type" not in s or not s.get("db_type"):
            s["db_type"] = "oscar"


_server_service: ServerService | None = None


def get_server_service(settings: Settings) -> ServerService:
    global _server_service
    if _server_service is None:
        from ..repositories import get_server_repo

        _server_service = ServerService(get_server_repo(settings), settings)
    return _server_service
