"""数据库适配器抽象 — 封装各库 CLI 方言、DDL 映射、SQL 函数与监控查询集。

新增数据库类型 = 新建一个子类并注册到 adapters/__init__.py。
"""
from __future__ import annotations

import shlex
from typing import Any


class DBAdapter:
    """数据库类型适配器基类。"""

    db_type: str = ""
    label: str = ""
    default_port: int = 2003
    default_user: str = "SYSDBA"
    default_db: str = "OSRDB"
    cli_tool: str = "isql"
    cli_heredoc: bool = True
    cli_win_file: bool = True
    cli_no_if_not_exists: bool = False

    # DDL 类型映射
    ddl_serial: str = "serial"
    ddl_boolean: str = "boolean"
    ddl_timestamp: str = "timestamp"
    ddl_text: str = "text"
    ddl_numeric: str = "numeric(10,3)"
    ddl_int: str = "int"
    ddl_varchar: str = "varchar"

    # 监控查询集 {category: {"label": str, "queries": {name: sql}}}
    query_sets: dict[str, dict[str, Any]] = {}

    # ── SQL 函数方言 ──
    def sql_now(self) -> str:
        return "now()"

    def sql_interval(self, days: int) -> str:
        return f"now() - interval '{days} days'"

    def sql_to_char(self, col: str) -> str:
        return f"to_char({col},'YYYY-MM-DD HH24:MI:SS')"

    def sql_cast_ts(self, v: str) -> str:
        return f"'{v}'::timestamp"

    def sql_concat(self, a: str, b: str) -> str:
        return f"coalesce({a},'')"

    def sql_from_dual(self) -> str:
        """无表 SELECT 需要的 FROM 子句；Oracle 需 'from dual'，其余方言返回空。"""
        return ""

    def sql_limit(self, n: int) -> str:
        """分页 LIMIT 方言。"""
        return f"limit {n}"

    # ── CLI 连接命令 ──
    def build_cli(self, server: dict[str, Any]) -> str:
        """根据服务器配置与自身方言构建 CLI 基础命令。"""
        cli = server.get("isql_cmd", "") or self.cli_tool
        host = server.get("db_host", "127.0.0.1")
        port = server.get("db_port", self.default_port)
        name = server.get("db_name", self.default_db)
        user = server.get("db_user", self.default_user)
        pwd = server.get("db_pass", "")
        win = server.get("os_type", "linux") == "windows"

        if self.db_type in ("oscar", "shentong"):
            cred = shlex.quote(f"{user}/{pwd}" if pwd else user)
            return f"{cli} -h {host} -p {port} -d {name} -U {cred}"
        if self.db_type == "mysql":
            pwd_part = f" -p{pwd}" if pwd else ""
            return f"{cli} -h {host} -P {port} -u {user}{pwd_part} {name}"
        if self.db_type in ("postgresql", "pg"):
            if win and pwd:
                return f"set PGPASSWORD={pwd}&& {cli} -h {host} -p {port} -U {user} -d {name}"
            env = f"PGPASSWORD={shlex.quote(pwd)} " if pwd else ""
            return f"{env}{cli} -h {host} -p {port} -U {user} -d {name}"
        if self.db_type == "oracle":
            cred = f"{user}/{pwd}" if pwd else user
            return f"{cli} -S {cred}@{host}:{port}/{name}"
        cred = shlex.quote(f"{user}/{pwd}" if pwd else user)
        return f"{cli} -h {host} -p {port} -d {name} -U {cred}"

    def quote_ident(self, ident: str) -> str:
        return ident

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DBAdapter {self.db_type}: {self.label}>"
