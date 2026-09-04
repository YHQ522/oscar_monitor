"""CLI SQL 执行层 — 构建命令、本地/SSH 执行、输出解析。

采集（collector）与日志持久化（persist）共用本层，避免循环依赖。
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from threading import Event
from typing import Any

from ..adapters import get_adapter
from .constants import HEADER_TRANSLATE
from .ssh import is_win, need_ssh, run_local, safe_decode, ssh_connect, ssh_exec, strip_ansi

# 数据库错误输出特征（神通/MySQL/PG/Oracle 各种 CLI 错误格式）
_DB_ERROR_PAT = re.compile(
    r"ST-\d+\s*:\s*ERROR|^\s*ERROR\b|ORA-\d{4,}|SP2-\d{4,}|"
    r"^psql:\s*ERROR|ERROR\s+\d{4,5}\s*\(",
    re.IGNORECASE | re.MULTILINE,
)


def output_has_error(out: str) -> bool:
    """判断 CLI 输出是否包含数据库错误（部分 CLI 出错时退出码仍为 0）。"""
    return bool(_DB_ERROR_PAT.search(strip_ansi(out or "")))


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


def ssh_exec_sql(client: Any, server: dict[str, Any], sql: str, timeout: float = 120) -> tuple[str, str, int]:
    """通过已建立的 SSH 连接执行 SQL。

    远程 Windows 目标机：SQL 通过 stdin 管道传入 CLI（Windows OpenSSH 无 heredoc，
    本地写的临时文件对远程不可见，文件重定向会报"系统找不到指定的文件"）。
    Linux：写入远程 /tmp 临时文件后重定向执行（与旧版行为一致）。
    """
    if is_win(server):
        cli = get_adapter(server.get("db_type")).build_cli(server)
        stdin, stdout, stderr = client.exec_command(f'cmd /c "{cli}"', timeout=timeout)
        try:
            stdin.write(sql.encode("utf-8"))
        finally:
            stdin.channel.shutdown_write()
        out = safe_decode(stdout.read())
        err = safe_decode(stderr.read())
        ec = stdout.channel.recv_exit_status()
        return out, err, ec
    sql_file = temp_sql_path(server)
    _, cmd = build_sql_cmd(server, sql, sql_file)
    return ssh_exec(client, cmd, timeout=timeout)


def exec_sql(server: dict[str, Any], sql: str, timeout: float = 120) -> tuple[str, str, int]:
    """执行 SQL，自动选择本地或 SSH。返回 (out, err, exit_code)。"""
    if need_ssh(server):
        client = ssh_connect(server, timeout=15)
        try:
            return ssh_exec_sql(client, server, sql, timeout=timeout)
        finally:
            client.close()
    sql_file = temp_sql_path(server)
    _, cmd = build_sql_cmd(server, sql, sql_file)
    return run_local(cmd, timeout=timeout)


def ssh_exec_sql_interruptible(
    client: Any,
    server: dict[str, Any],
    sql: str,
    cancel_event: Event | None = None,
    timeout: float = 60,
) -> tuple[str, str, int]:
    """执行 SQL（支持中断）：cancel_event 置位后立即终止远程查询。

    通过 channel 非阻塞轮询读取输出，避免 stdout.read() 阻塞导致无法取消。
    取消时向远端发送精确 pkill（按唯一临时文件名匹配），确保 CLI 进程被杀掉
    （仅关闭 SSH channel 不保证远端进程退出，实测会残留 bash+isql）。
    """
    sql_file: str | None = None
    if is_win(server):
        cli = get_adapter(server.get("db_type")).build_cli(server)
        stdin, stdout, stderr = client.exec_command(f'cmd /c "{cli}"', timeout=timeout)
        try:
            stdin.write(sql.encode("utf-8"))
        finally:
            stdin.channel.shutdown_write()
    else:
        sql_file = temp_sql_path(server)
        _, cmd = build_sql_cmd(server, sql, sql_file)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)

    deadline = time.time() + timeout
    chunks: list[bytes] = []
    err_chunks: list[bytes] = []

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    while True:
        if cancelled():
            # Linux：显式杀掉远端 bash 与 isql 进程（按唯一临时文件名精确匹配）。
            # 文件名含 8 位随机 hex，其他进程不会匹配，不会误杀。
            # 通过拆分变量拼接模式，避免执行本命令的 bash 自身 cmdline 含完整模式
            # 而被 pkill 自匹配杀掉（那样 pkill -9 兜底将不执行）。
            if sql_file:
                stem = os.path.basename(sql_file)[:-4]  # oscar_xxxxxxxx
                head, tail = stem[:6], stem[6:]         # 拆为 oscar_ 与 8 位 hex
                kill_cmd = (
                    f"H={head}; T={tail}; "
                    f"pkill -f \"$H$T[.]sql\" 2>/dev/null; sleep 0.3; "
                    f"pkill -9 -f \"$H$T[.]sql\" 2>/dev/null; true"
                )
                try:
                    _in, _out, _err = client.exec_command(kill_cmd, timeout=15)
                    _out.channel.recv_exit_status()
                except Exception:  # noqa: BLE001
                    pass
            try:
                stdout.channel.close()
            except Exception:  # noqa: BLE001
                pass
            return safe_decode(b"".join(chunks)), "执行已取消（页面已关闭）", -1
        if stdout.channel.recv_ready():
            chunk = stdout.channel.recv(65536)
            if chunk:
                chunks.append(chunk)
        if stderr.channel.recv_stderr_ready():
            chunk = stderr.channel.recv_stderr(65536)
            if chunk:
                err_chunks.append(chunk)
        if stdout.channel.exit_status_ready():
            # 进程已退出：排空剩余输出
            while stdout.channel.recv_ready():
                chunks.append(stdout.channel.recv(65536))
            while stderr.channel.recv_stderr_ready():
                err_chunks.append(stderr.channel.recv_stderr(65536))
            break
        if time.time() > deadline:
            try:
                stdout.channel.close()
            except Exception:  # noqa: BLE001
                pass
            raise TimeoutError(f"SQL 执行超过 {timeout:g} 秒，已中断")
        time.sleep(0.05)

    ec = stdout.channel.recv_exit_status()
    return safe_decode(b"".join(chunks)), safe_decode(b"".join(err_chunks)), ec


def run_local_interruptible(
    cmd: str,
    cancel_event: Event | None = None,
    timeout: float = 60,
) -> tuple[str, str, int]:
    """本地执行 SQL（支持中断）：cancel_event 置位后 terminate/kill 进程。"""
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.time() + timeout
    while proc.poll() is None:
        if cancel_event is not None and cancel_event.is_set():
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            out, err = proc.communicate(timeout=10)
            return safe_decode(out), "执行已取消（页面已关闭）", -1
        if time.time() > deadline:
            proc.kill()
            out, err = proc.communicate(timeout=10)
            raise TimeoutError(f"SQL 执行超过 {timeout:g} 秒，已中断")
        time.sleep(0.05)
    out, err = proc.communicate(timeout=10)
    return safe_decode(out), safe_decode(err), proc.returncode


# ═══════════════ 输出解析 ═══════════════
_MERGE_MARK_RE = re.compile(r"^\s*===Q:([^=]+)===\s*$")


def build_merged_sql(all_queries: list[tuple[str, str, str]]) -> str:
    """多查询合并脚本：每条查询前插入标记查询（SELECT '===Q:cat:qname==='）。

    标记查询输出固定三行（表头/分隔线/标记值），解析时按标记行分割，
    从而用一次 isql 会话执行全部采集查询（避免每条查询重复启动 CLI）。
    """
    parts: list[str] = []
    for cat, qname, sql in all_queries:
        q = sql.strip().rstrip(";").strip()
        parts.append(f"SELECT '===Q:{cat}:{qname}===' AS ___Q___;")
        parts.append(q + ";")
    return "\n".join(parts) + "\n"


def parse_merged_isql_output(output: str) -> dict[str, str]:
    """按标记行分割合并输出 → {'cat:qname': 查询输出块文本}。"""
    blocks: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for raw in output.splitlines():
        m = _MERGE_MARK_RE.match(raw.strip())
        if m:
            if current is not None:
                blocks[current] = "\n".join(buf)
            current = m.group(1)
            buf = []
        elif current is not None:
            buf.append(raw)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


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
        # 无竖线分隔的输出（单列结果）：跳过表头行及其紧跟的虚线分隔行
        # 形如 " COUNT\n-------\n 0"，否则表头会被误当作数据行
        data_rows: list[str] = []
        i = 0
        while i < len(clean_lines):
            line = clean_lines[i]
            if re.match(r"^-{3,}$", line):
                i += 1
                continue
            # 当前行是列名，紧跟虚线分隔行 → 跳过二者
            if i + 1 < len(clean_lines) and re.match(r"^-{3,}$", clean_lines[i + 1]):
                i += 2
                continue
            data_rows.append(line)
            i += 1
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
