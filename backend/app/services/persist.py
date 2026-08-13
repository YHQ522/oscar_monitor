"""日志持久化服务 — 将采集到的错误/慢 SQL 写入 log_db（可远程/本地），复用 core 执行层。

log_db 配置（host/port/user/pass/dbname/isql/db_type/ssh_*）转换为 server 形式后复用 exec_sql。
"""
from __future__ import annotations

import platform
import threading
from typing import Any

from ..adapters import get_adapter
from ..config import Settings
from ..core.db_exec import exec_sql, parse_isql_output

LOG_TABLE = "oscar_log_collect"

_ERROR_KEYWORDS = ("error", "fail", "unable", "cannot", "拒绝", "失败", "错误")


def safe_str(v: Any, maxlen: int = 1000, backslash: bool = False) -> str:
    """SQL 值转义；backslash=True 用于 MySQL（默认模式反斜杠是转义符）。"""
    s = (str(v or "")).replace("'", "''")
    if backslash:
        s = s.replace("\\", "\\\\")
    return s[:maxlen]


class LogPersistService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._table_created = False

    # ── 配置 ──
    def _log_cfg(self) -> dict[str, Any]:
        return self.settings.log_db or {}

    def _enabled(self) -> bool:
        return self.settings.log_enabled

    def _is_mysql(self) -> bool:
        """日志库是否为 MySQL（默认模式需额外转义反斜杠防注入）。"""
        return str(self._log_cfg().get("db_type", "")).lower() in ("mysql", "mariadb")

    def _server_cfg(self) -> dict[str, Any]:
        """把 log_db 配置转换为 server 形式，复用 core.db_exec.exec_sql。"""
        db = self._log_cfg()
        adapter = get_adapter(db.get("db_type"))
        return {
            "db_host": db.get("host", "127.0.0.1"),
            "db_port": db.get("port", adapter.default_port),
            "db_user": db.get("user", adapter.default_user),
            "db_pass": db.get("pass", ""),
            "db_name": db.get("dbname", adapter.default_db),
            "db_type": db.get("db_type", "oscar"),
            "isql_cmd": db.get("isql", "") or adapter.cli_tool,
            "ssh_host": db.get("ssh_host", ""),
            "ssh_port": db.get("ssh_port", 22),
            "ssh_user": db.get("ssh_user", "root"),
            "ssh_pass": db.get("ssh_pass", ""),
            "os_type": "windows" if platform.system() == "Windows" else "linux",
        }

    def _exec_sql(self, sql: str) -> None:
        """执行 SQL；isql 可能返回 0 但仍输出错误，需检测关键字。"""
        server = self._server_cfg()
        out, err, ec = exec_sql(server, sql, timeout=15)
        if ec != 0:
            raise RuntimeError((err or out or f"exit code {ec}").strip()[:500])
        output = (out + err).lower()
        if any(kw in output for kw in _ERROR_KEYWORDS):
            raise RuntimeError((err or out or "数据库执行失败").strip()[:500])

    # ── 建表 ──
    def _ensure_table(self) -> bool:
        if self._table_created:
            return True
        if not self._enabled():
            return False
        db = self._log_cfg()
        adapter = get_adapter(db.get("db_type"))
        vc = adapter.ddl_varchar

        ddl = f"""
create table {LOG_TABLE} (
    id           {adapter.ddl_serial} primary key,
    server_name  {vc}(200),
    check_type   {vc}(50),
    error_msg    {adapter.ddl_text},
    occur_time   {adapter.ddl_timestamp} default {adapter.sql_now()},
    exec_user    {vc}(100),
    exec_tool    {vc}(100),
    exec_sql     {adapter.ddl_text},
    cost_seconds {adapter.ddl_numeric},
    occur_count  {adapter.ddl_int} default 1
)""".strip()

        if adapter.cli_no_if_not_exists:  # Oracle 无 IF NOT EXISTS
            ddl_escaped = ddl.replace("'", "''")
            sql = f"""BEGIN
  EXECUTE IMMEDIATE '{ddl_escaped}';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE != -955 THEN RAISE; END IF;
END;"""
        else:
            sql = ddl.replace("create table", "create table if not exists", 1)

        self._exec_sql(sql.strip())
        self._table_created = True
        return True

    # ── 写入 ──
    def persist_db_error(self, server_name: str, log_entry: dict[str, Any]) -> None:
        if not self._enabled() or not log_entry.get("msg"):
            return
        with self._lock:
            if not self._ensure_table():
                return
        adapter = get_adapter(self._log_cfg().get("db_type"))
        bs = self._is_mysql()
        sname = safe_str(server_name, backslash=bs)
        msg = safe_str(log_entry.get("msg", ""), backslash=bs)
        euser = safe_str(log_entry.get("user", ""), backslash=bs)
        etool = safe_str(log_entry.get("tool", ""), backslash=bs)
        esql = safe_str(log_entry.get("sql", ""), backslash=bs)
        cost = log_entry.get("cost", 0) or 0
        otime = safe_str(log_entry.get("time", ""), backslash=bs)
        cast_ts = adapter.sql_cast_ts
        concat = adapter.sql_concat
        self._exec_sql(f"""
insert into {LOG_TABLE} (server_name, check_type, error_msg, occur_time, exec_user, exec_tool, exec_sql, cost_seconds)
select '{sname}', 'db_error', '{msg}', {cast_ts(otime)}, '{euser}', '{etool}', '{esql}', {cost}
{adapter.sql_from_dual()}
where not exists (
    select 1 from {LOG_TABLE}
    where server_name='{sname}' and error_msg='{msg}' and {concat('exec_sql','')}='{esql}'
);
update {LOG_TABLE} set occur_count=occur_count+1
where server_name='{sname}' and error_msg='{msg}' and {concat('exec_sql','')}='{esql}';
""")

    def persist_slow_sql(self, server_name: str, sql_entry: dict[str, Any]) -> None:
        if not self._enabled():
            return
        with self._lock:
            if not self._ensure_table():
                return
        bs = self._is_mysql()
        sname = safe_str(server_name, backslash=bs)
        msg = safe_str(sql_entry.get("sql", ""), 800, backslash=bs)
        cost = float(sql_entry.get("cost", 0) or 0)
        self._exec_sql(f"""
insert into {LOG_TABLE} (server_name, check_type, error_msg, cost_seconds)
select '{sname}', 'slow_sql', '{msg}', {cost}
{adapter.sql_from_dual()}
where not exists (
    select 1 from {LOG_TABLE}
    where server_name='{sname}' and check_type='slow_sql' and error_msg='{msg}'
);
update {LOG_TABLE} set occur_count=occur_count+1, cost_seconds={cost}
where server_name='{sname}' and check_type='slow_sql' and error_msg='{msg}';
""")

    def persist_os_error(self, server_name: str, check_type: str, error_msg: str) -> None:
        if not self._enabled() or not error_msg or not error_msg.strip():
            return
        with self._lock:
            if not self._ensure_table():
                return
        bs = self._is_mysql()
        safe_msg = safe_str(error_msg, 500, backslash=bs)
        safe_server = safe_str(server_name, backslash=bs)
        safe_type = safe_str(check_type, backslash=bs)
        self._exec_sql(f"""
insert into {LOG_TABLE} (server_name, check_type, error_msg)
select '{safe_server}', '{safe_type}', '{safe_msg}'
{adapter.sql_from_dual()}
where not exists (
    select 1 from {LOG_TABLE}
    where server_name='{safe_server}' and check_type='{safe_type}' and error_msg='{safe_msg}'
);
update {LOG_TABLE} set occur_count=occur_count+1
where server_name='{safe_server}' and check_type='{safe_type}' and error_msg='{safe_msg}';
""")

    def cleanup_old_logs(self) -> None:
        if not self._enabled():
            return
        with self._lock:
            if not self._ensure_table():
                return
        days = self.settings.log_retention_days
        adapter = get_adapter(self._log_cfg().get("db_type"))
        self._exec_sql(f"delete from {LOG_TABLE} where occur_time < {adapter.sql_interval(days)};")

    # ── 查询 ──
    def query_logs(self, server_name: str, limit: int = 200) -> list[dict[str, Any]]:
        if not self._enabled() or not self._ensure_table():
            return []
        adapter = get_adapter(self._log_cfg().get("db_type"))
        safe_server = safe_str(server_name, backslash=self._is_mysql())
        to_char = adapter.sql_to_char
        concat = adapter.sql_concat
        sql = (
            f"select check_type, error_msg, occur_count, {to_char('occur_time')}, "
            f"{concat('exec_user','')}, {concat('exec_tool','')}, {concat('exec_sql','')}, "
            f"coalesce(cost_seconds,0) from {LOG_TABLE} "
            f"where server_name='{safe_server}' order by occur_time desc {adapter.sql_limit(limit)};"
        )
        server = self._server_cfg()
        out, err, ec = exec_sql(server, sql, timeout=15)
        if ec != 0 and not out.strip():
            return []
        parsed = parse_isql_output(out, "logs")
        columns = parsed.get("columns", [])
        rows = parsed.get("rows", [])
        result: list[dict[str, Any]] = []
        for row in rows:
            rec: dict[str, Any] = {}
            for idx, col in enumerate(columns):
                val = row[idx] if idx < len(row) else ""
                if col.lower() == "occur_count":
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        pass
                if col.lower() == "cost_seconds":
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                rec[col.lower()] = val
            result.append(rec)
        return result


_log_service: LogPersistService | None = None


def get_log_service(settings: Settings) -> LogPersistService:
    global _log_service
    if _log_service is None:
        _log_service = LogPersistService(settings)
    return _log_service
