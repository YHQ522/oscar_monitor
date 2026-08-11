"""仓储层 — 抽象接口与工厂。

存储后端可拔插：默认 JSON 文件，可切换 SQLAlchemy(SQLite/PostgreSQL 等)。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..config import Settings


class ServerRepository(ABC):
    @abstractmethod
    def list(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get(self, server_id: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def save_all(self, servers: list[dict[str, Any]]) -> None:
        ...

    @abstractmethod
    def delete(self, server_id: str) -> None:
        ...


class UserRepository(ABC):
    @abstractmethod
    def list(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def get(self, username: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def save_all(self, users: list[dict[str, Any]]) -> None:
        ...

    @abstractmethod
    def delete(self, username: str) -> None:
        ...


def get_server_repo(settings: Settings) -> ServerRepository:
    if settings.storage_backend == "sqlite":
        from .sql_repos import SqliteServerRepository

        return SqliteServerRepository(settings)
    from .json_repos import JsonServerRepository

    return JsonServerRepository(settings)


def get_user_repo(settings: Settings) -> UserRepository:
    if settings.storage_backend == "sqlite":
        from .sql_repos import SqliteUserRepository

        return SqliteUserRepository(settings)
    from .json_repos import JsonUserRepository

    return JsonUserRepository(settings)
