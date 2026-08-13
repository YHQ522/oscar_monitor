"""采集服务 — SSH 采集数据库/OS 指标、连接测试、启停管控。

仅依赖 core 与 adapters 层，不再反向依赖数据层。
"""
from __future__ import annotations

import re
import shlex
import subprocess
import time
from typing import Any

from ..adapters import get_query_sets
from ..config import Settings, get_settings
from ..core.constants import DB_RELATED_OS_CHECKS, OS_CHECKS_LINUX, OS_CHECKS_WIN
from ..core.db_exec import build_sql_cmd, parse_isql_output, parse_table_output, temp_sql_path
from ..core.ssh import is_win, need_ssh, run_local, ssh_connect, ssh_exec, strip_ansi, translate_error
from ..core.constants import DB_ERROR_TRANSLATE, SSH_ERROR_TRANSLATE, SSH_FIX_LINUX, SSH_FIX_WIN


def _cfg() -> Settings:
    """采集/管控超时参数从 Settings 读取，便于按需调优（OSCAR_* 环境变量）。"""
    return get_settings()


# ═══════════════ 采集 ═══════════════
def collect_sql_queries(server: dict[str, Any], enabled_categories: list[str]) -> dict[str, Any]:
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
    client = None
    try:
        if remote:
            client = ssh_connect(server)
        sql_timeout = _cfg().ssh_exec_timeout
        for cat, qname, sql in all_queries:
            sql_file = temp_sql_path(server)
            _, cmd = build_sql_cmd(server, sql, sql_file)
            try:
                if remote:
                    out, err, ec = ssh_exec(client, cmd, timeout=sql_timeout)
                else:
                    out, err, ec = run_local(cmd, timeout=sql_timeout)
            except Exception as e:  # noqa: BLE001
                results.setdefault(cat, {})[qname] = {"query": qname, "error": str(e), "columns": [], "rows": []}
                continue
            if ec != 0 and not out.strip():
                results.setdefault(cat, {})[qname] = {"query": qname, "error": err or "执行失败", "columns": [], "rows": []}
            else:
                results.setdefault(cat, {})[qname] = parse_isql_output(out, qname)
    finally:
        if client:
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
        parts = ln.split(None, 1)
        if len(parts) == 2 and not parts[0].lower().startswith(("pid", "名称", "name")):
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


def _parse_os_check(check_name: str, raw: str) -> dict[str, Any]:
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


def collect_os_info(server: dict[str, Any], enabled_os_checks: list[str]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    os_checks = _os_checks_map(server)
    cmds = [(n, os_checks[n]) for n in enabled_os_checks if n in os_checks]
    if not cmds:
        return results

    remote = need_ssh(server)
    use_ps = is_win(server)
    sep = "OSCAR_OS_SEP"

    # Windows 下命令含引号嵌套，逐个执行更稳妥
    if use_ps:
        for check_name, cmd in cmds:
            os_timeout = _cfg().os_cmd_timeout
            try:
                if remote:
                    client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
                    try:
                        out, err, ec = ssh_exec(client, cmd + " 2>&1", timeout=os_timeout)
                    finally:
                        client.close()
                else:
                    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=os_timeout)
                    out, err, ec = proc.stdout, proc.stderr, proc.returncode
                raw = out.strip() or err.strip()
                result = _parse_os_check(check_name, raw)
                result["error"] = "" if raw else (err.strip()[:500] if err else "")
                result["exit_code"] = ec
                results[check_name] = result
            except Exception as e:  # noqa: BLE001
                results[check_name] = {"output": "", "error": str(e), "exit_code": -1}
        return results

    # Linux：分隔符合并执行，减少 SSH 往返
    qsep = shlex.quote(sep)
    cmds_str = ("; echo " + qsep + "; ").join(c for _, c in cmds)
    full_cmd = "(" + "echo " + qsep + "; " + cmds_str + ")"

    os_timeout = _cfg().os_cmd_timeout
    try:
        if remote:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            try:
                out, err, ec = ssh_exec(client, full_cmd, timeout=os_timeout)
            finally:
                client.close()
        else:
            out, err, ec = run_local(full_cmd, timeout=os_timeout)
    except Exception as e:  # noqa: BLE001
        out, err, ec = "", str(e), -1

    blocks = out.split(sep)
    for i, (check_name, _) in enumerate(cmds):
        raw = blocks[i + 1] if i + 1 < len(blocks) else ""
        result = _parse_os_check(check_name, raw)
        if not result["output"] and err:
            result["error"] = err.strip()[:500]
        results[check_name] = result
    return results


def collect_apps(server: dict[str, Any]) -> list[dict[str, Any]]:
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
    try:
        if remote:
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            try:
                out, err, ec = ssh_exec(client, full_cmd, timeout=app_timeout)
            finally:
                client.close()
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
    return {
        "server": server.get("name", server.get("ssh_host", "unknown")),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "os_info": collect_os_info(server, enabled_os_checks),
        "db_queries": collect_sql_queries(server, enabled_categories),
        "apps": collect_apps(server),
    }


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

    sql_file = temp_sql_path(server)
    _, cmd = build_sql_cmd(server, "SELECT VERSION();", sql_file)
    db_timeout = min(_cfg().ssh_exec_timeout, 60)
    try:
        if need_ssh(server):
            client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
            try:
                out, err, ec = ssh_exec(client, cmd, timeout=db_timeout)
            finally:
                client.close()
        else:
            out, err, ec = run_local(cmd, timeout=db_timeout)
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
def db_control(server: dict[str, Any], action: str) -> dict[str, Any]:
    if not need_ssh(server):
        return {"ok": False, "msg": "仅支持远程SSH操作"}

    svc_name = server.get("svc_name", "oscardb_OSRDBd")
    svc_mgr = server.get("svc_mgr", "service")
    if is_win(server):
        agent = "oscaragentd"
        cmd = {
            "start": f"sc start {agent} & sc start {svc_name}",
            "stop": f"sc stop {svc_name} & sc stop {agent}",
            "restart": f"sc stop {svc_name} & sc stop {agent} & sc start {agent} & sc start {svc_name}",
            "status": f"sc query {svc_name} & sc query {agent} & tasklist /FI \"IMAGENAME eq oscar.exe\" 2>nul",
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
        cmd = {
            "start": f"{p}{agent} start; {p}{svc_name} start",
            "stop": f"{p}{svc_name} stop; {p}{agent} stop",
            "restart": f"{p}{svc_name} stop; {p}{agent} stop; {p}{agent} start; {p}{svc_name} start",
            "status": "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10",
        }.get(action, "ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10")

    cmd += " 2>&1"
    client = ssh_connect(server, timeout=_cfg().ssh_connect_timeout)
    try:
        out, err, ec = ssh_exec(client, cmd, timeout=_cfg().control_cmd_timeout)
    finally:
        client.close()

    out = strip_ansi(out)
    status_lines = [l.strip() for l in out.split("\n") if l.strip()]
    running = any(re.search(r"[/\\]oscar\b", l) and "oscaragent" not in l.lower() for l in status_lines)

    if action == "status":
        return {"ok": True, "action": "status", "running": running,
                "output": "\n".join(status_lines),
                "msg": "数据库运行中" if running else "数据库未运行"}
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
