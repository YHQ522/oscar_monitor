"""JSON 文件仓储实现（默认后端），兼容旧版 data/servers.json 与 data/users.json。"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

from ..config import Settings
from . import ServerRepository, UserRepository


def _read_json(path: str, default: list) -> list:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else default
    except (json.JSONDecodeError, OSError):
        return default


def _write_json(path: str, data: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class JsonServerRepository(ServerRepository):
    def __init__(self, settings: Settings):
        self.file = str(settings.servers_file)
        self._lock = threading.Lock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return _read_json(self.file, [])

    def get(self, server_id: str) -> dict[str, Any] | None:
        for s in self.list():
            if s.get("id") == server_id:
                return s
        return None

    def save_all(self, servers: list[dict[str, Any]]) -> None:
        with self._lock:
            _write_json(self.file, servers)

    def delete(self, server_id: str) -> None:
        with self._lock:
            servers = _read_json(self.file, [])
            servers = [s for s in servers if s.get("id") != server_id]
            _write_json(self.file, servers)


class JsonUserRepository(UserRepository):
    def __init__(self, settings: Settings):
        self.file = str(settings.users_file)
        self._lock = threading.Lock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return _read_json(self.file, [])

    def get(self, username: str) -> dict[str, Any] | None:
        for u in self.list():
            if u.get("username") == username:
                return u
        return None

    def save_all(self, users: list[dict[str, Any]]) -> None:
        with self._lock:
            _write_json(self.file, users)

    def delete(self, username: str) -> None:
        with self._lock:
            users = _read_json(self.file, [])
            users = [u for u in users if u.get("username") != username]
            _write_json(self.file, users)
