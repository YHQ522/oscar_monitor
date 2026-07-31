"""CLI SQL 执行层 — 构建命令、本地/SSH 执行、输出解析。

采集（collector）与日志持久化（persist）共用本层，避免循环依赖。
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from ..adapters import get_adapter
from .constants import HEADER_TRANSLATE
from .ssh import is_win, need_ssh, run_local, ssh_connect, ssh_exec, strip_ansi


def temp_sql_path(server: dict[str, Any]) -> str:
    uid = uuid.uuid4().hex[:8]
    return f"C:/Windows/Temp/oscar_{uid}.sql" if is_win(server) else f"/tmp/oscar_{uid}.sql"


def build_sql_cmd(server: dict[str, Any], sql: str, sql_file: str) -> tuple[str, str]:
    """返回 (sql, 完整 shell 命令)。保持与旧版行为一致。"""
    adapter = get_adapter(server.get("db_type"))
    cli = adapter.build_cli(server)
    win = is_win(server)

    if win:
        try:
            with open(sql_file, "w", encoding="utf-8") as f:
                f.write(sql)
        except OSError:
            pass
        if adapter.db_type in ("postgresql", "pg"):
            return (sql, f"cmd /c \"{cli} -f {sql_file} && del {sql_file}\"")
        return (sql, f"cmd /c \"{cli} < {sql_file} && del {sql_file}\"")
    return (
        sql,
        f"cat > {sql_file} << 'OSCAREOF'\n{sql}\nOSCAREOF\n{cli} < {sql_file} 2>&1; R=$?; rm -f {sql_file}; exit $R",
    )


def exec_sql(server: dict[str, Any], sql: str, timeout: float = 120) -> tuple[str, str, int]:
    """执行 SQL，自动选择本地或 SSH。返回 (out, err, exit_code)。"""
    sql_file = temp_sql_path(server)
    _, cmd = build_sql_cmd(server, sql, sql_file)
    if need_ssh(server):
        client = ssh_connect(server, timeout=15)
        try:
            return ssh_exec(client, cmd, timeout=timeout)
        finally:
            client.close()
    return run_local(cmd, timeout=timeout)


# ═══════════════ 输出解析 ═══════════════
def parse_isql_output(output: str, query_name: str) -> dict[str, Any]:
    """解析 isql 类管道输出为 {columns, rows}。"""
    output = strip_ansi(output)
    lines = output.strip().split("\n")
    clean_lines: list[str] = []
    skip_next = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        lower = s.lower()
        if lower == "connect to:" or lower.startswith("connect to:"):
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if lower.startswith("using new protocol"):
            continue
        if lower.startswith("logon database at time"):
            continue
        if lower.startswith("logout database at time"):
            continue
        if lower.startswith("sql=>"):
            continue
        if s.startswith("(") and ("row" in lower or "行" in lower):
            continue
        clean_lines.append(s)

    if not clean_lines:
        return {"query": query_name, "columns": [], "rows": [], "raw": output}

    header_line: list[str] | None = None
    data_start = 0
    for i, line in enumerate(clean_lines):
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                header_line = parts
                data_start = i + 1
                break

    if header_line is None:
        data_rows = [l for l in clean_lines if not re.match(r"^-{3,}$", l)]
        return {"query": query_name, "columns": ["结果"], "rows": [[l] for l in data_rows], "raw": output}

    rows: list[list[str]] = []
    for line in clean_lines[data_start:]:
        if re.match(r"^-{3,}$", line):
            continue
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        # 跳过分隔线（如 ---------+--------）
        if all(re.fullmatch(r"[-+]+", p or "") for p in parts):
            continue
        if len(parts) >= len(header_line):
            rows.append(parts[: len(header_line)])
        elif parts:
            rows.append(parts)

    return {"query": query_name, "columns": header_line, "rows": rows, "raw": output}


def parse_table_output(output: str) -> dict[str, Any] | None:
    """解析空格分隔的表格式输出（free/df 等）。"""
    output = strip_ansi(output)
    lines = output.strip().split("\n")
    headers: list[str] | None = None
    rows: list[list[str]] = []
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        first = parts[0].lower().replace("/", "").replace(":", "").replace("\\", "")
        if first in ("filesystem", "文件系统", "totalmb", "name"):
            headers = parts
            continue
        if not headers:
            headers = parts
            continue
        if len(parts) == len(headers) + 1:
            headers = [""] + headers
        if len(parts) >= len(headers):
            rows.append(parts[: len(headers)])
        else:
            rows.append(parts + [""] * (len(headers) - len(parts)))
    if headers and rows:
        # 处理 "Mounted on" 这类表头被拆成两列的情况
        if len(headers) >= 2 and headers[-1].lower() == "on":
            headers = headers[:-2] + ["Mounted on"]
            rows = [r[: len(headers)] for r in rows]
        headers = [HEADER_TRANSLATE.get(h.lower(), h) for h in headers]
        return {"columns": headers, "rows": rows}
    return None


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
