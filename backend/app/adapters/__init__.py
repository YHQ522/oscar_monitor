"""适配器注册表 — 新增数据库类型在这里注册。"""
from __future__ import annotations

from typing import Any

from .base import DBAdapter
from .mysql import MySqlAdapter
from .oracle import OracleAdapter
from .oscar import OscarAdapter
from .postgresql import PostgreSqlAdapter

_REGISTRY: dict[str, type[DBAdapter]] = {
    "oscar": OscarAdapter,
    "shentong": OscarAdapter,  # 向后兼容别名
    "mysql": MySqlAdapter,
    "postgresql": PostgreSqlAdapter,
    "pg": PostgreSqlAdapter,  # 向后兼容别名
    "oracle": OracleAdapter,
}

_registry_lock = None


def get_adapter(db_type: str | None) -> DBAdapter:
    """按 db_type 获取适配器实例（幂等，可缓存实例）。"""
    key = db_type or "oscar"
    return _REGISTRY.get(key, OscarAdapter)()


def get_query_sets(db_type: str | None) -> dict[str, dict[str, Any]]:
    return get_adapter(db_type).query_sets


def register(db_type: str, adapter_cls: type[DBAdapter]) -> None:
    """运行时注册自定义适配器。"""
    _REGISTRY[db_type] = adapter_cls


def all_adapters() -> dict[str, str]:
    """返回 {db_type: label}，用于前端下拉。"""
    seen: dict[str, str] = {}
    for key, cls in _REGISTRY.items():
        if key in ("shentong", "pg"):
            continue
        seen[key] = cls.label
    return seen
