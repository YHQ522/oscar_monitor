"""采集服务 — SSH 采集数据库/OS 指标、连接测试、启停管控。

仅依赖 core 与 adapters 层，不再反向依赖数据层。
"""
from __future__ import annotations

import re
import shlex
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any

from ..adapters import get_adapter, get_query_sets
from ..config import Settings, get_settings
from ..core.constants import DB_RELATED_OS_CHECKS, OS_CHECKS_LINUX, OS_CHECKS_WIN
from ..core.db_exec import (
    build_merged_sql,
    build_sql_cmd,
    exec_sql,
    output_has_error,
    parse_isql_output,
    parse_merged_isql_output,
    parse_table_output,
    ssh_exec_sql,
    temp_sql_path,
)
from ..core.ssh import is_win, need_ssh, run_local, ssh_connect, ssh_exec, strip_ansi, translate_error
from ..core.constants import DB_ERROR_TRANSLATE, SSH_ERROR_TRANSLATE, SSH_FIX_LINUX, SSH_FIX_WIN


def _cfg() -> Settings:
    """采集/管控超时参数从 Settings 读取，便于按需调优（OSCAR_* 环境变量）。"""
    return get_settings()


# ═══════════════ 采集 ═══════════════
def collect_sql_queries(server: dict[str, Any], enabled_categories: list[str], client: Any = None) -> dict[str, Any]:
    query_sets = get_query_sets(server.get("db_type"))
    results: dict[str, Any] = {}
    all_queries = [
        (cat, qname, sql)
        for cat in enabled_categories
        if cat in query_sets
        for qname, sql in query_sets[cat]["queries"].items()
    ]
    if not all_queries:
        return results

    remote = need_ssh(server)
    adapter = get_adapter(server.get("db_type"))
    own_client = False
    try:
        if remote and client is None:
            client = ssh_connect(server)
            own_client = True
        sql_timeout = _cfg().ssh_exec_timeout

        if adapter.merge_queries:
            # 合并为单次 CLI 会话执行全部查询（每条查询前插标记行），避免重复启动 CLI
            merged = build_merged_sql(all_queries)
            if remote:
                out, err, ec = ssh_exec_sql(client, server, merged, timeout=sql_timeout)
            else:
                sql_file = temp_sql_path(server)
                _, cmd = build_sql_cmd(server, merged, sql_file)
                out, err, ec = run_local(cmd, timeout=sql_timeout)
            global_err = (err or "").strip()
            blocks = parse_merged_isql_output(out)
            for cat, qname, _sql in all_queries:
                block = blocks.get(f"{cat}:{qname}")
                if not block or not block.strip():
                    # 无输出块：查询执行失败（错误信息通常在全局 err 中）
                    results.setdefault(cat, {})[qname] = {
                        "query": qname,
                        "error": (global_err or "查询无输出（可能执行失败）")[:500],
                        "columns": [], "rows": [],
                    }
                elif ec != 0 or output_has_error(block):
                    results.setdefault(cat, {})[qname] = {
                        "query": qname,
                        "error": (block or global_err or "执行失败").strip()[:500],
                        "columns": [], "rows": [],
                    }
                else:
                    results.setdefault(cat, {})[qname] = parse_isql_output(block, qname)
        else:
            for cat, qname, sql in all_queries:
                try:
                    if remote:
                        out, err, ec = ssh_exec_sql(client, server, sql, timeout=sql_timeout)
                    else:
                        sql_file = temp_sql_path(server)
                        _, cmd = build_sql_cmd(server, sql, sql_file)
                        out, err, ec = run_local(cmd, timeout=sql_timeout)
                except Exception as e:  # noqa: BLE001
                    results.setdefault(cat, {})[qname] = {"query": qname, "error": str(e), "columns": [], "rows": []}
                    continue
                if ec != 0 or output_has_error(out):
                    results.setdefault(cat, {})[qname] = {
                        "query": qname, "error": (err or out or "执行失败").strip()[:500], "columns": [], "rows": [],
                    }
                else:
                    results.setdefault(cat, {})[qname] = parse_isql_output(out, qname)
    finally:
        if client and own_client:
            client.close()
    return results


def _os_checks_map(server: dict[str, Any]) -> dict[str, str]:
    return OS_CHECKS_WIN if is_win(server) else OS_CHECKS_LINUX


def _parse_mem_structured(raw: str) -> dict[str, Any] | None:
    """Windows key=value 内存输出（TotalMB/FreeMB/UsedMB）→ 结构化行。

    该格式不是表格（单行 key=value），parse_table_output 会把首行当表头而无 rows，
    导致详情页显示"（无数据）"。此处显式解析为 指标/值 两列表格。
    """
    m = re.search(r"TotalMB=(\d+).*?FreeMB=(\d+).*?UsedMB=(\d+)", raw)
    if not m:
        return None
    total_m, free_m, used_m = int(m.group(1)), int(m.group(2)), int(m.group(3))

    def fmt(mb: int) -> str:
        return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"

    pct = round(used_m / total_m * 100, 1) if total_m > 0 else 0.0
    return {
        "columns": ["指标", "值"],
        "rows": [
            ["总内存", fmt(total_m)],
            ["已用", fmt(used_m)],
            ["可用", fmt(free_m)],
            ["使用率", f"{pct}%"],
        ],
    }


def _parse_win_disk(raw: str) -> dict[str, Any] | None:
    """Windows 'X 12.3GB/45.6GB' 磁盘输出 → 结构化行（含使用率列）。

    修复两个问题：① 首行被 parse_table_output 误当表头导致首个盘符丢失；
    ② 原 columns 无"使用率"列，前端 DiskUsage 无法渲染进度条。
    """
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    disk_re = re.compile(r"^([A-Za-z])\s+([\d.]+)GB/([\d.]+)GB$")
    rows: list[list[str]] = []
    for ln in lines:
        m = disk_re.match(ln)
        if not m:
            return None  # 存在非该格式的行 → 不是 Windows 磁盘格式，走通用解析
        drive, used_gb, total_gb = m.group(1), float(m.group(2)), float(m.group(3))
        pct = round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0.0
        rows.append([drive, f"{used_gb} GB", f"{total_gb} GB", f"{pct}%"])
    return {"columns": ["盘符", "已用", "总量", "使用率"], "rows": rows}


def _parse_cpu_structured(raw: str) -> dict[str, Any] | None:
    """CPU 输出人性化结构化：概况（使用率/负载/运行时长）+ 占用最高的进程列表。

    原 parse_table_output 会把首行 `LoadPercentage=27 Source=avg` 当表头、
    把 `---` 分隔线当数据行，且进程列的 CPU 占用语义不清晰。
    Windows 输出形如：
        LoadPercentage=27 Source=avg
        ---
        GTA5_Enhanced 42338.609375
    Linux 输出形如：
        ... up 3 days, 1 user, load average: 0.00, 0.01, 0.05
        ---
        top -bn1 表格（PID USER ... 表头 + 进程行）
    概况从文本正则提取；进程列表取 --- 之后的"名称 占用"行，忽略 top 表头。
    """
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    summary: list[dict[str, str]] = []
    m = re.search(r"LoadPercentage[= ]*(\d+)", raw)
    if m:
        summary.append({"label": "CPU 使用率", "value": f"{int(m.group(1))}%"})
    else:
        m = re.search(r"(\d+\.?\d*)\s*id\b", raw)
        if m:
            summary.append({"label": "CPU 使用率", "value": f"{round(100 - float(m.group(1)), 1)}%"})
    m = re.search(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", raw)
    if m:
        summary.append({"label": "负载(1/5/15 分钟)", "value": f"{m.group(1)} / {m.group(2)} / {m.group(3)}"})
    m = re.search(r"up\s+(.+?),\s+\d+\s+user", raw)
    if m:
        summary.append({"label": "运行时长", "value": m.group(1).strip()})
    procs: list[list[str]] = []
    started = False
    for ln in lines:
        if ln.startswith("---"):
            started = True
            continue
        if not started:
            continue
        parts = ln.split()
        if len(parts) < 2:
            continue
        first = parts[0].lower()
        # 跳过 top 输出的标题/汇总行（top、Tasks、%Cpu(s)、MiB/KiB、Swap 等）
        if first.startswith(("pid", "名称", "name", "top", "task", "%cpu", "mib", "kib", "gib", "swap")):
            continue
        # Linux top 表格行：PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
        if len(parts) >= 11 and parts[0].isdigit():
            procs.append([parts[-1], parts[8]])
        else:
            procs.append([parts[0], parts[1]])
    if not summary and not procs:
        return None
    return {"summary": summary, "columns": ["进程", "CPU 占用"], "rows": procs[:10]}


def _parse_os_errors_structured(raw: str) -> dict[str, Any] | None:
    """操作系统日志错误 → 结构化行（时间 + 内容），多行续行合并到上一条。

    Windows（Get-EventLog）输出形如：
        2026-07-31 21:58:54 安装失败: Windows 安装下列更新失败，错误为 0x80073d02: ...
        2026-07-31 19:58:20 由于下列错误，luafv 服务启动失败:
        %%1275
    Linux（/var/log/messages grep）输出形如：
        Jul 31 21:58:54 hostname program[pid]: error message
        ===FAIL===
        ...
    以行首时间前缀识别新记录；无时间前缀的行视为上一条的续行。
    """
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    time_re = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    )
    rows: list[list[str]] = []
    for ln in lines:
        if ln.startswith("==="):  # Linux 分段标记（===FAIL===），跳过
            continue
        m = time_re.match(ln)
        if m:
            rows.append([m.group(1), ln[m.end():].strip()])
        elif rows:
            rows[-1][1] = (rows[-1][1] + " " + ln).strip()
        else:
            rows.append(["", ln])
    if not rows:
        return None
    return {"columns": ["时间", "错误内容"], "rows": rows}


# ═══════════════ 数据库错误日志（elog）采集 ═══════════════
_ELOG_CACHE_TTL = 86400  # 日志路径缓存有效期（秒），到期后重新搜索
_ELOG_TAIL_LINES = 500   # 每个日志文件最多取的行数
_ELOG_LEVEL_RE = "ERROR|FATAL|PANIC|WARNING"
# server_name -> (缓存时间, 日志目录列表)；缓存目录避免每 30s 全盘 find 扫描
_elog_paths_cache: dict[str, tuple[float, list[str]]] = {}


def _parse_db_log_errors_structured(raw: str, hours: float | None = None) -> dict[str, Any] | None:
    """数据库 elog 日志输出 → 结构化行（文件/时间/级别/内容），最新在前。

    输出形如：
        ===FILE:/opt/ShenTong/log/elog_xxx.txt===
        2026-08-17 10:18:30, /*Main*/ LOG, version: ...
        2026-08-17 10:18:30, /*Main*/ NOTICE, 参数 ...
    无时间前缀的行视为上一条的续行。
    hours>0 时只保留最近 N 小时内的行（时间窗过滤，避免反复拖回老日志）。
    """
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if not lines:
        return None
    cutoff: datetime | None = None
    if hours and hours > 0:
        cutoff = datetime.now() - timedelta(hours=hours)
    rows: list[list[str]] = []
    current_file = ""
    time_re = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")
    for ln in lines:
        if ln.startswith("===FILE:"):
            current_file = ln[len("===FILE:"):].rstrip("=").strip()
            continue
        if ln.startswith("*"):  # 文件之间的分隔线
            continue
        m = time_re.match(ln)
        if m:
            try:
                ts = datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = None
            if cutoff is not None and ts is not None and ts < cutoff:
                continue  # 时间窗之外的旧行
            rest = ln[m.end():].lstrip(", ").strip()
            level = ""
            lv = re.match(r"(?:/\*.*?\*/\s*)?(ERROR|FATAL|PANIC|WARNING|NOTICE|LOG)\b", rest)
            if lv:
                level = lv.group(1)
                rest = rest[lv.end():].lstrip(", ").strip()
            rows.append([current_file.rsplit("/", 1)[-1], m.group(1), level, rest])
        elif rows:
            rows[-1][3] = (rows[-1][3] + " " + ln).strip()
        else:
            rows.append(["", "", "", ln])
    if not rows:
        return None
    rows.reverse()  # 最新在前
    return {"columns": ["文件", "时间", "级别", "内容"], "rows": rows}


def _elog_tail_pipe() -> str:
    """读取文件尾部并过滤错误级别行的 shell 管道片段。"""
    return (
        'while read f; do echo "===FILE:$f==="; '
        + f"tail -{_ELOG_TAIL_LINES} \"$f\" 2>/dev/null | grep -iE '{_ELOG_LEVEL_RE}'; done"
    )


def _collect_elog_output(server: dict[str, Any], client: Any) -> str:
    """采集数据库错误日志输出：优先缓存目录/配置路径，兜底全盘扫描。

    首次（或缓存过期）全盘 find 按修改时间取最新 3 个 elog 文件并缓存其目录；
    后续采集直接 ls -t 缓存目录下的 elog*，自动跟随日志轮转，避免每 30s 全盘扫描。
    """
    name = server.get("name") or server.get("ssh_host", "")
    cfg = str(server.get("elog_path") or "").strip()
    os_timeout = _cfg().os_cmd_timeout

    def _run(cmd: str) -> str:
        if client is not None:
            out, _, _ = ssh_exec(client, cmd, timeout=os_timeout)
            return out
        out, _, _ = run_local(cmd, timeout=os_timeout)
        return out

    tail_pipe = _elog_tail_pipe()

    # 1) 缓存目录命中 → 直接取最新文件（跟随轮转），输出含标记才算有效
    cached = _elog_paths_cache.get(name)
    if not cfg and cached and time.time() - cached[0] < _ELOG_CACHE_TTL and cached[1]:
        globs = " ".join(f'"{d}/elog*" 2>/dev/null' for d in cached[1])
        out = _run(f"ls -t {globs} | head -3 | {tail_pipe}")
        if "===FILE:" in out:
            return out
        _elog_paths_cache.pop(name, None)  # 缓存失效（文件被清理/移动）

    # 2) 配置路径 / 全盘搜索
    if cfg:
        globs = " ".join(f'"{p.strip()}" 2>/dev/null' for p in cfg.split(",") if p.strip())
        cmd = f"ls -t {globs} | head -3 | {tail_pipe}"
    else:
        cmd = (
            "find / -maxdepth 5 -name 'elog*' -type f -printf '%T@ %p\\n' 2>/dev/null "
            f"| sort -rn | head -3 | cut -d' ' -f2- | {tail_pipe}"
        )
    out = _run(cmd)
    paths = [p.strip() for p in re.findall(r"===FILE:(.+?)===", out)]
    if paths:
        _elog_paths_cache[name] = (time.time(), _elog_dirs_from_output(out))
    return out


def _elog_dirs_from_output(raw: str) -> list[str]:
    """从采集输出提取 elog 文件所在目录（兼容 Linux '/' 与 Windows '\\' 路径）。"""
    paths = [p.strip() for p in re.findall(r"===FILE:(.+?)===", raw)]
    dirs = sorted({p.replace("\\", "/").rsplit("/", 1)[0] or "/" for p in paths})
    return dirs


def _win_elog_cmd(server: dict[str, Any]) -> tuple[str, bool]:
    """Windows db_log_errors 采集命令。

    目录缓存命中时只扫缓存目录（跟随日志轮转，避免每次全盘递归）；
    缓存缺失/失效时回退全盘搜索。返回 (命令, 是否缓存命中)。
    """
    name = server.get("name") or server.get("ssh_host", "")
    cfg = str(server.get("elog_path") or "").strip()
    cached = _elog_paths_cache.get(name)
    tail_filter = (
        f"Get-Content $_.FullName -Tail {_ELOG_TAIL_LINES} -ErrorAction SilentlyContinue "
        "| Select-String -Pattern 'ERROR','FATAL','PANIC','WARNING' | ForEach-Object { Write-Host $_.Line }"
    )
    if not cfg and cached and time.time() - cached[0] < _ELOG_CACHE_TTL and cached[1]:
        dirs = ",".join(f"'{d}'" for d in cached[1])
        return (
            'powershell -Command "Get-ChildItem ' + dirs
            + " -Filter 'elog*' -ErrorAction SilentlyContinue "
            "| Sort-Object LastWriteTime -Descending | Select-Object -First 3 | "
            "ForEach-Object { Write-Host ('===FILE:'+$_.FullName+'==='); " + tail_filter + " }\"",
            True,
        )
    if cfg:
        dirs = ",".join(f"'{p.strip().replace(chr(92), chr(47))}'" for p in cfg.split(",") if p.strip())
        return (
            'powershell -Command "Get-ChildItem ' + dirs
            + " -Filter 'elog*' -ErrorAction SilentlyContinue "
            "| Sort-Object LastWriteTime -Descending | Select-Object -First 3 | "
            "ForEach-Object { Write-Host ('===FILE:'+$_.FullName+'==='); " + tail_filter + " }\"",
            False,
        )
    return OS_CHECKS_WIN["db_log_errors"], False


def _parse_os_check(check_name: str, raw: str, elog_hours: float = 24) -> dict[str, Any]:
    result: dict[str, Any] = {"output": strip_ansi(raw).strip(), "error": "", "exit_code": 0}
    if check_name == "memory":
        parsed = _parse_mem_structured(raw) or parse_table_output(raw)
        if parsed:
            result["columns"] = parsed["columns"]
            result["rows"] = parsed["rows"]
    elif check_name == "disk":
        parsed = _parse_win_disk(raw) or parse_table_output(raw)
        if parsed:
            result["columns"] = parsed["columns"]
            result["rows"] = parsed["rows"]
    elif check_name == "cpu":
        parsed = _parse_cpu_structured(raw) or parse_table_output(raw)
        if parsed:
            result["columns"] = parsed["columns"]
            result["rows"] = parsed["rows"]
            if parsed.get("summary"):
                result["summary"] = parsed["summary"]
    elif check_name == "os_errors":
        parsed = _parse_os_errors_structured(raw)
        if parsed:
            result["columns"] = parsed["columns"]
            result["rows"] = parsed["rows"]
    elif check_name == "install_path":
        # 安装路径为纯文本列表（每行一个路径），无表头，显式转为单列表格
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            result["columns"] = ["路径"]
            result["rows"] = [[ln] for ln in lines]
    elif check_name == "db_log_errors":
        parsed = _parse_db_log_errors_structured(raw, hours=elog_hours)
        if parsed:
            result["columns"] = parsed["columns"]
            result["rows"] = parsed["rows"]
    if check_name == "cpu":
        if "load average" in raw:
            m = re.search(r"load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", raw)
        else:
            m = re.search(r"LoadPercentage[= ]*(\d+)", raw)
        if m:
            result["load_1m"] = m.group(1)
            try:
                result["load_5m"] = m.group(2)
                result["load_15m"] = m.group(3)
            except IndexError:
                pass
        m2 = re.search(r"up\s+(.+?),\s+\d+\s+user", raw)
        if m2:
            result["uptime"] = m2.group(1).strip()
    return result


def _win_os_merged_cmd(cmds: list[tuple[str, str]], sep: str) -> str:
    """多个 Windows OS 检查命令合并为一次 PowerShell 进程执行。

    每个检查命令提取其 `-Command "..."` 内部脚本后按标记 Write-Host 拼接，
    避免 5 个检查各自冷启动 PowerShell（每个约 1-2 秒）。
    """
    inners: list[str] = []
    for _, cmd in cmds:
        c = cmd.strip()
        if c.startswith("powershell -Command"):
            c = c[len("powershell -Command"):].strip()
        if c.startswith('"') and c.endswith('"'):
            c = c[1:-1]
        inners.append(c)
    body = ("; Write-Host '" + sep + "'; ").join(inners)
    return f"powershell -Command \"$ErrorActionPreference='SilentlyContinue'; Write-Host '{sep}'; " + body + '"'


def collect_os_info(server: dict[str, Any], enabled_os_checks: list[str], client: Any = None) -> dict[str, Any]:
    results: dict[str, Any] = {}
    os_checks = _os_checks_map(server)
    # db_log_errors 单独采集（路径缓存/时间窗逻辑），其余系统检查合并执行
    cmds = [(n, os_checks[n]) for n in enabled_os_checks if n in os_checks and n != "db_log_errors"]
    has_elog = "db_log_errors" in enabled_os_checks and "db_log_errors" in os_checks
    elog_hours = float(server.get("elog_hours", 24) or 24)
    if not cmds and not has_elog:
        return results

    remote = need_ssh(server)
    use_ps = is_win(server)
    sep = "OSCAR_OS_SEP"

    # Windows 下命令含引号嵌套，但复用一个 SSH 连接逐个执行，避免多次握手拖慢采集
    if use_ps:
        os_timeout = _cfg().os_cmd_timeout
        own_client = False
        if client is None and remote:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            own_client = True

        def _ps_run(cmd: str) -> tuple[str, str, int]:
            if remote:
                return ssh_exec(client, cmd + " 2>&1", timeout=os_timeout)
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=os_timeout)
            return proc.stdout, proc.stderr, proc.returncode

        try:
            # 合并为一次 PowerShell 进程执行全部检查（标记行分隔），避免每个检查单独冷启动
            merged_cmd = _win_os_merged_cmd(cmds, sep)
            try:
                out, err, ec = _ps_run(merged_cmd)
            except Exception as e:  # noqa: BLE001
                for check_name, _cmd in cmds:
                    results[check_name] = {"output": "", "error": str(e), "exit_code": -1}
                out, err, ec = "", "", -1
            blocks = out.split(sep)
            for i, (check_name, _cmd) in enumerate(cmds):
                raw = (blocks[i + 1] if i + 1 < len(blocks) else "").strip()
                result = _parse_os_check(check_name, raw)
                result["error"] = "" if raw else (err.strip()[:500] if err else "")
                result["exit_code"] = ec if raw else (result.get("exit_code", ec))
                results[check_name] = result

            # Windows 目标机的数据库错误日志：带目录缓存，避免每次全盘递归扫描
            if has_elog:
                name = server.get("name") or server.get("ssh_host", "")
                elog_cmd, cached = _win_elog_cmd(server)
                try:
                    out, err, ec = _ps_run(elog_cmd)
                except Exception as e:  # noqa: BLE001
                    results["db_log_errors"] = {"output": "", "error": str(e), "exit_code": -1}
                    return results
                raw = out.strip() or err.strip()
                if cached and "===FILE:" not in raw:
                    _elog_paths_cache.pop(name, None)  # 缓存失效（文件被清理/移动），全盘重搜一次
                    elog_cmd, _ = _win_elog_cmd(server)
                    try:
                        out, err, ec = _ps_run(elog_cmd)
                    except Exception as e:  # noqa: BLE001
                        results["db_log_errors"] = {"output": "", "error": str(e), "exit_code": -1}
                        return results
                    raw = out.strip() or err.strip()
                if "===FILE:" in raw:
                    _elog_paths_cache[name] = (time.time(), _elog_dirs_from_output(raw))
                result = _parse_os_check("db_log_errors", raw, elog_hours)
                result["error"] = "" if raw else (err.strip()[:500] if err else "")
                result["exit_code"] = ec
                results["db_log_errors"] = result
        finally:
            if client and own_client:
                client.close()
        return results

    # Linux：分隔符合并执行，减少 SSH 往返
    qsep = shlex.quote(sep)
    cmds_str = ("; echo " + qsep + "; ").join(c for _, c in cmds)
    full_cmd = "(" + "echo " + qsep + "; " + cmds_str + ")"

    os_timeout = _cfg().os_cmd_timeout
    own_client = False
    try:
        if remote and client is None:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            own_client = True
        if remote:
            out, err, ec = ssh_exec(client, full_cmd, timeout=os_timeout)
        else:
            out, err, ec = run_local(full_cmd, timeout=os_timeout)
    except Exception as e:  # noqa: BLE001
        out, err, ec = "", str(e), -1
    finally:
        if client and own_client:
            client.close()

    blocks = out.split(sep)
    for i, (check_name, _) in enumerate(cmds):
        raw = blocks[i + 1] if i + 1 < len(blocks) else ""
        result = _parse_os_check(check_name, raw, elog_hours)
        if not result["output"] and err:
            result["error"] = err.strip()[:500]
        results[check_name] = result

    # 数据库错误日志单独采集：路径缓存 + 按修改时间取最新文件 + 级别过滤
    if has_elog:
        try:
            if remote:
                client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
                try:
                    elog_raw = _collect_elog_output(server, client)
                finally:
                    client.close()
            else:
                elog_raw = _collect_elog_output(server, None)
            result = _parse_os_check("db_log_errors", elog_raw, elog_hours)
            if not result["output"] and err:
                result["error"] = err.strip()[:500]
            results["db_log_errors"] = result
        except Exception as e:  # noqa: BLE001
            results["db_log_errors"] = {"output": "", "error": str(e), "exit_code": -1}
    return results


def collect_apps(server: dict[str, Any], client: Any = None) -> list[dict[str, Any]]:
    apps = server.get("apps", [])
    if not apps:
        return []
    results: list[dict[str, Any]] = []
    remote = need_ssh(server)
    win = is_win(server)

    if win:
        parts = "; ".join(
            f'Write-Host \\"===={a.get("name", a.get("port", ""))}====\\"; if (netstat -ano | Select-String \\":{a["port"]}\\\") {{ Write-Host \\"RUNNING\\" }} else {{ Write-Host \\"STOPPED\\" }}'
            for a in apps
        )
        full_cmd = f'powershell -Command "{parts}"'
    else:
        full_cmd = "; ".join(
            f'echo "===={a.get("name", a.get("port", ""))}===="; ss -tlnp | grep -q ":{a["port"]} " && echo "RUNNING" || echo "STOPPED"'
            for a in apps
        )

    app_timeout = _cfg().app_cmd_timeout
    own_client = False
    try:
        if remote and client is None:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            own_client = True
        if remote:
            out, err, ec = ssh_exec(client, full_cmd, timeout=app_timeout)
        else:
            out, err, ec = run_local(full_cmd, timeout=app_timeout)

        blocks = re.split(r"====(.+?)====", out)
        i = 1
        while i + 1 < len(blocks):
            app_label = blocks[i].strip()
            running = "RUNNING" in blocks[i + 1].strip()
            results.append({"name": app_label, "running": running, "status": "运行中" if running else "已停止"})
            i += 2
    except Exception as e:  # noqa: BLE001
        for a in apps:
            results.append({"name": a.get("name", str(a.get("port", ""))), "running": False, "status": "检查失败: " + str(e)[:100]})
    finally:
        if client and own_client:
            client.close()
    return results


def collect_all(
    server: dict[str, Any],
    enabled_categories: list[str] | None = None,
    enabled_os_checks: list[str] | None = None,
) -> dict[str, Any]:
    query_sets = get_query_sets(server.get("db_type"))
    if enabled_categories is None:
        enabled_categories = list(query_sets.keys())
    if enabled_os_checks is None:
        enabled_os_checks = list(OS_CHECKS_LINUX.keys())
    if server.get("skip_db"):
        # 仅系统监控：不采集任何数据库内容，并排除依赖数据库的系统检查项
        enabled_categories = []
        enabled_os_checks = [c for c in enabled_os_checks if c not in DB_RELATED_OS_CHECKS]
    # SSH 连接复用：一次采集全程仅一次握手（SQL + OS + 应用状态共用）
    remote = need_ssh(server)
    client = None
    try:
        if remote:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
        return {
            "server": server.get("name", server.get("ssh_host", "unknown")),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "os_info": collect_os_info(server, enabled_os_checks, client),
            "db_queries": collect_sql_queries(server, enabled_categories, client),
            "apps": collect_apps(server, client),
        }
    finally:
        if client:
            client.close()


# ═══════════════ 连接测试 ═══════════════
def test_connection(server: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {"ssh": {"ok": False, "msg": ""}, "db": {"ok": False, "msg": "", "version": ""}}
    # 统一判定：skip_db 显式标记，或未启用任何数据库采集类别，都视为跳过数据库
    skip_db = server.get("skip_db", False) or not (server.get("enabled_categories") or [])

    if need_ssh(server):
        fix_map = SSH_FIX_WIN if is_win(server) else SSH_FIX_LINUX
        try:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            client.close()
            results["ssh"] = {"ok": True, "msg": "连接成功"}
        except Exception as e:  # noqa: BLE001
            results["ssh"]["msg"] = translate_error(str(e), SSH_ERROR_TRANSLATE, fix_map)
            return results
    else:
        results["ssh"] = {"ok": True, "msg": "无需远程连接（本地或未配置）"}

    if skip_db:
        results["db"] = {"ok": True, "msg": "跳过（未选数据库采集项）"}
        return results
    if not server.get("db_pass"):
        results["db"]["msg"] = "数据库密码不能为空"
        return results

    db_timeout = min(_cfg().ssh_exec_timeout, 60)
    try:
        # 统一走 exec_sql：远程 Windows 通过 stdin 管道传 SQL，避免远程临时文件问题
        out, err, ec = exec_sql(server, "SELECT VERSION();", timeout=db_timeout)
    except Exception as e:  # noqa: BLE001
        results["db"]["msg"] = translate_error(str(e), DB_ERROR_TRANSLATE)
        return results

    if ec == 0 and out.strip():
        results["db"] = {"ok": True, "msg": "数据库连接成功", "version": out.strip().split("\n")}
    else:
        error_text = (err or out or "").strip()
        results["db"]["msg"] = translate_error(error_text, DB_ERROR_TRANSLATE)
    return results


# ═══════════════ 启停管控 ═══════════════
# 进程探测与兜底终止：oscar 数据库主进程（oscar -o normal）与 agent（oscaragent ... -c）
_PROBE_CMD = "ps -eo pid,cmd | grep -v grep | grep -E '[o]scar|[o]scaragent'"
_KILL_SOFT = "pkill -f '[o]scaragent[[:space:]].*-c'; pkill -f '[o]scar[[:space:]]-o[[:space:]]normal'; true"
_KILL_HARD = "pkill -9 -f '[o]scaragent[[:space:]].*-c'; pkill -9 -f '[o]scar[[:space:]]-o[[:space:]]normal'; true"


def _leftover_procs(client: Any) -> list[str]:
    """返回远程残留的 oscar / oscaragent 进程行（无残留返回空列表）。"""
    out, _, _ = ssh_exec(client, _PROBE_CMD, timeout=15)
    return [l.strip() for l in out.splitlines() if l.strip()]


# svc_name 支持的变量占位符（{db_name} 等），取值来自服务器配置字段
_SVC_NAME_VARS = ("db_name", "db_host", "db_user", "db_type", "name", "ssh_host")


def _resolve_svc_name(server: dict[str, Any]) -> str:
    """解析数据库服务名：支持 {变量} 占位符，留空时按数据库类型/系统自动推导。

    留空推导（避免 oscar 命名规则套用到其他数据库）：
        oscar/Linux       → oscardb_<库名>d（如 oscardb_OSRDBd）
        oscar/Windows     → OSCARDB_<库名>_SERVER（如 OSCARDB_OSRDB_SERVER）
        mysql             → mysqld
        postgresql        → postgresql
        oracle            → oracle
    示例：
        svc_name = "oscardb_{db_name}d"  → oscardb_OSRDBd
        svc_name = "oracle_{db_host}"    → oracle_192.168.1.10
    未知占位符或格式错误时原样返回，由后续命令执行时报错提示。
    """
    raw = str(server.get("svc_name") or "").strip()
    if not raw:
        db_type = get_adapter(server.get("db_type")).db_type
        dbname = str(server.get("db_name") or "OSRDB").strip()
        if is_win(server) and db_type == "oscar":
            raw = f"OSCARDB_{dbname}_SERVER"
        else:
            raw = {
                "oscar": f"oscardb_{dbname}d",
                "mysql": "mysqld",
                "postgresql": "postgresql",
                "oracle": "oracle",
            }.get(db_type, f"oscardb_{dbname}d")
    values = {k: str(server.get(k) or "") for k in _SVC_NAME_VARS}
    try:
        return raw.format(**values)
    except (KeyError, ValueError):
        return raw


def db_control(server: dict[str, Any], action: str) -> dict[str, Any]:
    if not need_ssh(server):
        return {"ok": False, "msg": "仅支持远程SSH操作"}

    svc_name = _resolve_svc_name(server)
    svc_mgr = server.get("svc_mgr", "service")
    if is_win(server):
        # Windows 目标机：sc 命令管理服务（svc_mgr 不适用）。
        # 神通 Windows 服务名：数据库 OSCARDB_<实例名>_SERVER、agent 为 OscarAgent
        agent = str(server.get("svc_agent") or "OscarAgent").strip()
        cmd = {
            "start": f"sc start {agent} & sc start {svc_name}",
            "stop": f"sc stop {svc_name} & sc stop {agent}",
            "restart": f"sc stop {svc_name} & sc stop {agent} & sc start {agent} & sc start {svc_name}",
            "status": (
                f"sc query {svc_name} & sc query {agent} & "
                "tasklist /FI \"IMAGENAME eq oscar.exe\" & tasklist /FI \"IMAGENAME eq oscaragent.exe\""
            ),
        }.get(action, f"sc query {svc_name}")
    elif svc_mgr == "systemctl":
        agent = "oscaragentd"
        cmd = {
            "start": f"systemctl start {agent}; systemctl start {svc_name}",
            "stop": f"systemctl stop {svc_name}; systemctl stop {agent}",
            "restart": f"systemctl stop {svc_name}; systemctl stop {agent}; systemctl start {agent}; systemctl start {svc_name}",
            "status": "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10",
        }.get(action, "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10")
    elif svc_mgr == "service":
        agent = "oscaragentd"
        cmd = {
            "start": f"service {agent} start; service {svc_name} start",
            "stop": f"service {svc_name} stop; service {agent} stop",
            "restart": f"service {svc_name} stop; service {agent} stop; service {agent} start; service {svc_name} start",
            "status": "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10",
        }.get(action, "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10")
    elif svc_mgr == "script":
        start_cmd = server.get("svc_start_cmd", "")
        stop_cmd = server.get("svc_stop_cmd", "")
        if action == "start":
            cmd = start_cmd
        elif action == "stop":
            cmd = stop_cmd
        elif action == "restart":
            cmd = f"{stop_cmd} && sleep 2 && {start_cmd}" if stop_cmd and start_cmd else ""
        else:
            cmd = "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10"
        if not cmd.strip():
            return {"ok": False, "action": action, "msg": "请先配置脚本命令"}
    else:
        p = svc_mgr.rstrip("/") + "/"
        agent = "oscaragentd"
        # 服务注册生成的数据库脚本固定命名为 oscardb_<实例名>d；
        # 配置的 svc_name 若不是该格式，回退到该命名规则
        db_script = svc_name if svc_name.startswith("oscardb_") else f"oscardb_{svc_name}d"
        db = f'if [ -x "{p}{svc_name}" ]; then "{p}{svc_name}" {{A}}; elif [ -x "{p}{db_script}" ]; then "{p}{db_script}" {{A}}; else echo "init script not found: {svc_name}"; exit 127; fi'
        ag = f'if [ -x "{p}{agent}" ]; then "{p}{agent}" {{A}}; else echo "init script not found: {agent}"; exit 127; fi'
        cmd = {
            "start": ag.format(A="start") + "; " + db.format(A="start"),
            "stop": db.format(A="stop") + "; " + ag.format(A="stop"),
            "restart": db.format(A="stop") + "; " + ag.format(A="stop") + "; " + ag.format(A="start") + "; " + db.format(A="start"),
            "status": _PROBE_CMD,
        }.get(action, _PROBE_CMD)

    cmd += " 2>&1"
    client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
    try:
        out, err, ec = ssh_exec(client, cmd, timeout=_cfg().control_cmd_timeout)
        leftovers: list[str] = []
        # 停止后验证：服务脚本的 stop 对异常进程可能无效（如 agent 死循环不响应
        # 停止请求），残留进程先优雅终止，仍无法退出则强杀
        if action == "stop":
            time.sleep(2)
            if is_win(server):
                # Windows：tasklist 验证进程，残留用 taskkill /F 强杀
                probe = (
                    "tasklist /FI \"IMAGENAME eq oscar.exe\" & "
                    "tasklist /FI \"IMAGENAME eq oscaragent.exe\""
                )
                out2, _, _ = ssh_exec(client, probe, timeout=_cfg().control_cmd_timeout)
                leftovers = [
                    l.strip() for l in out2.splitlines()
                    if l.strip() and ("oscar.exe" in l.lower() or "oscaragent.exe" in l.lower())
                ]
                if leftovers:
                    ssh_exec(client, "taskkill /F /IM oscar.exe /T & taskkill /F /IM oscaragent.exe /T",
                             timeout=_cfg().control_cmd_timeout)
                    time.sleep(2)
                    out2, _, _ = ssh_exec(client, probe, timeout=_cfg().control_cmd_timeout)
                    leftovers = [
                        l.strip() for l in out2.splitlines()
                        if l.strip() and ("oscar.exe" in l.lower() or "oscaragent.exe" in l.lower())
                    ]
            else:
                leftovers = _leftover_procs(client)
                if leftovers:
                    ssh_exec(client, _KILL_SOFT, timeout=_cfg().control_cmd_timeout)
                    time.sleep(2)
                    leftovers = _leftover_procs(client)
                    if leftovers:
                        ssh_exec(client, _KILL_HARD, timeout=_cfg().control_cmd_timeout)
                        time.sleep(1)
                        leftovers = _leftover_procs(client)
    finally:
        client.close()

    out = strip_ansi(out)
    status_lines = [l.strip() for l in out.split("\n") if l.strip()]
    if is_win(server):
        # Windows：tasklist 输出行含 oscar.exe 为数据库进程；sc query 的服务状态作为参考
        running = any("oscar.exe" in l.lower() and "oscaragent" not in l.lower() for l in status_lines)
    else:
        running = any(re.search(r"[/\\]oscar\b", l) and "oscaragent" not in l.lower() for l in status_lines)

    if action == "status":
        return {"ok": True, "action": "status", "running": running,
                "output": "\n".join(status_lines),
                "msg": "数据库运行中" if running else "数据库未运行"}
    if action == "stop":
        if leftovers:
            return {"ok": False, "action": "stop",
                    "msg": f"停止失败：仍有 {len(leftovers)} 个进程残留，请人工处理",
                    "output": "\n".join(leftovers[:20])}
        return {"ok": True, "action": "stop", "msg": "操作成功，相关进程已停止", "output": out.strip()[:500]}
    if ec == 0:
        return {"ok": True, "action": action, "msg": "操作成功", "output": out.strip()[:500]}
    return {"ok": False, "action": action, "msg": (err or out or "操作失败")[:300], "output": (err or out)[:500]}


def app_control(server: dict[str, Any], app_name: str, action: str) -> dict[str, Any]:
    if not need_ssh(server):
        return {"ok": False, "msg": "仅支持远程SSH操作"}

    apps = server.get("apps", [])
    app = next((a for a in apps if a.get("name") == app_name), None)
    if not app:
        return {"ok": False, "msg": f"应用 {app_name} 不存在"}

    port = app.get("port")
    svc_name = app.get("svc_name", app_name)
    win = is_win(server)

    if action == "status":
        status_cmd = app.get("status_cmd", "")
        if status_cmd:
            cmd = status_cmd + " 2>&1"
        elif win:
            cmd = f"powershell -Command \"if (netstat -ano | Select-String ':{port}')) {{ Write-Host 'RUNNING' }} else {{ Write-Host 'STOPPED' }}\""
        else:
            cmd = f'ss -tlnp | grep -q ":{port} " && echo "RUNNING" || echo "STOPPED"'
        cmd += " 2>&1"
        try:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            try:
                out, err, ec = ssh_exec(client, cmd, timeout=_cfg().app_cmd_timeout)
            finally:
                client.close()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "action": "status", "app": app_name, "msg": f"状态查询失败: {e}"}
        running = "RUNNING" in (out or "")
        return {"ok": True, "action": "status", "app": app_name, "running": running,
                "msg": f"{app_name} 运行中" if running else f"{app_name} 已停止"}

    if action == "start" and app.get("start_cmd"):
        cmd = app["start_cmd"]
    elif action == "stop" and app.get("stop_cmd"):
        cmd = app["stop_cmd"]
    elif action == "restart" and app.get("stop_cmd") and app.get("start_cmd"):
        cmd = app["stop_cmd"] + "; sleep 2; " + app["start_cmd"]
    else:
        svc_mgr = app.get("svc_mgr", server.get("svc_mgr", "systemctl"))
        if win:
            cmd = f"sc stop {svc_name} & timeout /t 2 >nul & sc start {svc_name}" if action == "restart" else f"sc {action} {svc_name}"
        elif svc_mgr == "systemctl":
            cmd = f"systemctl {action} {svc_name}"
        elif svc_mgr == "service":
            cmd = f"service {svc_name} {'status' if action == 'status' else action}"
        else:
            p = svc_mgr.rstrip("/") + "/"
            cmd = f"{p}{svc_name} {action}"

    cmd = cmd.rstrip() + " 2>&1"
    try:
        client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
        try:
            out, err, ec = ssh_exec(client, cmd, timeout=_cfg().control_cmd_timeout)
        finally:
            client.close()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "action": action, "app": app_name, "msg": f"操作失败: {e}"}

    if ec == 0:
        return {"ok": True, "action": action, "app": app_name, "msg": f"{app_name} {action} 成功", "output": out.strip()[:1000]}
    return {"ok": False, "action": action, "app": app_name, "msg": (err or out or "操作失败")[:500], "output": (err or out)[:1000]}
