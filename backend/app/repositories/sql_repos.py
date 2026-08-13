"""SQLAlchemy 仓储实现 — SQLite 后端，结构可扩展到 PostgreSQL/MySQL。

服务器/用户的关键字段用列存储，列表/嵌套结构用 JSON 列，保持与 JSON 后端一致的字典接口。
"""
from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import Column, Integer, String, Text, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config import Settings
from . import ServerRepository, UserRepository

Base = declarative_base()

SERVER_FIELDS = [
    "name", "ssh_host", "ssh_port", "ssh_user", "ssh_pass",
    "db_host", "db_port", "db_user", "db_pass", "db_name", "db_type",
    "isql_cmd", "auto_refresh", "os_type", "in_control", "persist_enabled",
    "svc_name", "svc_mgr", "svc_start_cmd", "svc_stop_cmd",
    "enabled_categories", "enabled_os_checks", "apps", "skip_db", "created_at",
]


class ServerRow(Base):
    __tablename__ = "servers"

    id = Column(String(20), primary_key=True)
    name = Column(String(200), default="")
    ssh_host = Column(String(200), default="")
    ssh_port = Column(Integer, default=22)
    ssh_user = Column(String(100), default="root")
    ssh_pass = Column(String(200), default="")
    db_host = Column(String(200), default="127.0.0.1")
    db_port = Column(Integer, default=2003)
    db_user = Column(String(100), default="SYSDBA")
    db_pass = Column(String(200), default="")
    db_name = Column(String(100), default="OSRDB")
    db_type = Column(String(20), default="oscar")
    isql_cmd = Column(String(200), default="isql")
    auto_refresh = Column(Integer, default=0)
    os_type = Column(String(20), default="linux")
    in_control = Column(Integer, default=1)
    persist_enabled = Column(Integer, default=0)
    svc_name = Column(String(100), default="")
    svc_mgr = Column(String(50), default="systemctl")
    svc_start_cmd = Column(Text, default="")
    svc_stop_cmd = Column(Text, default="")
    enabled_categories = Column(Text, default="[]")  # JSON
    enabled_os_checks = Column(Text, default="[]")   # JSON
    apps = Column(Text, default="[]")                # JSON
    skip_db = Column(Integer, default=0)
    created_at = Column(String(40), default="")


class UserRow(Base):
    __tablename__ = "users"

    username = Column(String(100), primary_key=True)
    password = Column(String(200), default="")
    is_admin = Column(Integer, default=0)
    perms = Column(Text, default="[]")  # JSON
    created_at = Column(String(40), default="")


def _row_to_server(row: ServerRow) -> dict[str, Any]:
    def _loads(v: str, default: Any) -> Any:
        try:
            return json.loads(v) if v else default
        except (json.JSONDecodeError, TypeError):
            return default

    return {
        "id": row.id,
        "name": row.name or "",
        "ssh_host": row.ssh_host or "",
        "ssh_port": row.ssh_port or 22,
        "ssh_user": row.ssh_user or "",
        "ssh_pass": row.ssh_pass or "",
        "db_host": row.db_host or "",
        "db_port": row.db_port or 2003,
        "db_user": row.db_user or "",
        "db_pass": row.db_pass or "",
        "db_name": row.db_name or "",
        "db_type": row.db_type or "oscar",
        "isql_cmd": row.isql_cmd or "isql",
        "auto_refresh": row.auto_refresh or 0,
        "os_type": row.os_type or "linux",
        "in_control": bool(row.in_control),
        "persist_enabled": bool(row.persist_enabled),
        "svc_name": row.svc_name or "",
        "svc_mgr": row.svc_mgr or "systemctl",
        "svc_start_cmd": row.svc_start_cmd or "",
        "svc_stop_cmd": row.svc_stop_cmd or "",
        "enabled_categories": _loads(row.enabled_categories, []),
        "enabled_os_checks": _loads(row.enabled_os_checks, []),
        "apps": _loads(row.apps, []),
        "skip_db": bool(row.skip_db),
        "created_at": row.created_at or "",
    }


def _server_to_row(row: ServerRow, server: dict[str, Any]) -> ServerRow:
    for f in SERVER_FIELDS:
        if f not in server:
            continue
        v = server[f]
        if f in ("enabled_categories", "enabled_os_checks", "apps"):
            setattr(row, f, json.dumps(v, ensure_ascii=False))
        elif f in ("in_control", "persist_enabled", "skip_db"):
            setattr(row, f, 1 if v else 0)
        else:
            setattr(row, f, v)
    if not row.created_at:
        row.created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return row


def _row_to_user(row: UserRow) -> dict[str, Any]:
    try:
        perms = json.loads(row.perms) if row.perms else []
    except (json.JSONDecodeError, TypeError):
        perms = []
    return {
        "username": row.username,
        "password": row.password or "",
        "is_admin": bool(row.is_admin),
        "perms": perms,
        "created_at": row.created_at or "",
    }


def _user_to_row(row: UserRow, user: dict[str, Any]) -> UserRow:
    row.username = user.get("username", row.username)
    row.password = user.get("password", row.password)
    row.is_admin = 1 if user.get("is_admin") else 0
    row.perms = json.dumps(user.get("perms", []), ensure_ascii=False)
    if not row.created_at:
        row.created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    return row


class SqliteServerRepository(ServerRepository):
    def __init__(self, settings: Settings):
        url = f"sqlite:///{settings.db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})
        event.listen(self._engine, "connect", lambda dbapi_conn, rec: dbapi_conn.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(self._engine)
        self._session = sessionmaker(bind=self._engine, expire_on_commit=False)

    def list(self) -> list[dict[str, Any]]:
        with self._session() as s:
            return [_row_to_server(r) for r in s.query(ServerRow).order_by(ServerRow.created_at).all()]

    def get(self, server_id: str) -> dict[str, Any] | None:
        with self._session() as s:
            row = s.get(ServerRow, server_id)
            return _row_to_server(row) if row else None

    def save_all(self, servers: list[dict[str, Any]]) -> None:
        with self._session() as s:
            for server in servers:
                row = s.get(ServerRow, server.get("id"))
                if row is None:
                    row = ServerRow(id=server.get("id", ""))
                    s.add(row)
                _server_to_row(row, server)
            s.commit()

    def delete(self, server_id: str) -> None:
        with self._session() as s:
            row = s.get(ServerRow, server_id)
            if row:
                s.delete(row)
                s.commit()


class SqliteUserRepository(UserRepository):
    def __init__(self, settings: Settings):
        url = f"sqlite:///{settings.db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self._engine)
        self._session = sessionmaker(bind=self._engine, expire_on_commit=False)

    def list(self) -> list[dict[str, Any]]:
        with self._session() as s:
            return [_row_to_user(r) for r in s.query(UserRow).order_by(UserRow.created_at).all()]

    def get(self, username: str) -> dict[str, Any] | None:
        with self._session() as s:
            row = s.get(UserRow, username)
            return _row_to_user(row) if row else None

    def save_all(self, users: list[dict[str, Any]]) -> None:
        with self._session() as s:
            for user in users:
                row = s.get(UserRow, user.get("username", ""))
                if row is None:
                    row = UserRow(username=user.get("username", ""))
                    s.add(row)
                _user_to_row(row, user)
            s.commit()

    def delete(self, username: str) -> None:
        with self._session() as s:
            row = s.get(UserRow, username)
            if row:
                s.delete(row)
                s.commit()
