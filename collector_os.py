"""OS-level checks for Linux and Windows targets."""
import re
import shlex
import logging

_log = logging.getLogger('oscar_monitor.collector_os')

# Lazy imports from collector to avoid circular import (collector imports us)
_ssh_connect = None
_ssh_exec = None
strip_ansi = None
parse_table_output = None
_need_ssh = None
_is_win = None
_run_local = None


def _import_collector():
    """Lazy one-time import of collector helpers (avoids circular imports)."""
    global _ssh_connect, _ssh_exec, strip_ansi, parse_table_output
    global _need_ssh, _is_win, _run_local
    if _ssh_connect is not None:
        return
    from collector import _ssh_connect as _sc, _ssh_exec as _se
    from collector import strip_ansi as _sa, parse_table_output as _pto
    from collector import _need_ssh as _ns, _is_win as _iw, _run_local as _rl
    _ssh_connect = _sc
    _ssh_exec = _se
    strip_ansi = _sa
    parse_table_output = _pto
    _need_ssh = _ns
    _is_win = _iw
    _run_local = _rl

OS_CHECKS_LINUX = {
    "memory": "free -h 2>/dev/null || cat /proc/meminfo 2>/dev/null | head -20",
    "disk": "df -h 2>/dev/null",
    "cpu": "uptime 2>/dev/null; echo '---'; top -bn1 2>/dev/null | head -10 || echo 'top not available'",
    "install_path": "find / -maxdepth 4 -type d \\( -name 'oscar' -o -name 'ShenTong' \\) 2>/dev/null | head -5",
    "os_errors": "cat /var/log/messages* 2>/dev/null | grep -i error | tail -50; echo '===FAIL==='; cat /var/log/messages* 2>/dev/null | grep -i fail | tail -50",
    "db_log_errors": "find / -maxdepth 5 -name 'elog*' -type f 2>/dev/null | head -3 | while read f; do echo \"===FILE:$f===\"; tail -500 \"$f\" 2>/dev/null; done",
}

OS_CHECKS_WIN = {
    "memory": "powershell -Command \"$os=Get-CimInstance Win32_OperatingSystem; Write-Host ('TotalMB='+[math]::Round($os.TotalVisibleMemorySize/1024)+' FreeMB='+[math]::Round($os.FreePhysicalMemory/1024)+' UsedMB='+[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1024))\"",
    "disk": "powershell -Command \"Get-PSDrive -PSProvider FileSystem | Where-Object {$_.Used -gt 0} | ForEach-Object {Write-Host ($_.Name+' '+[math]::Round($_.Used/1GB,1)+'GB/'+[math]::Round(($_.Used+$_.Free)/1GB,1)+'GB')}\"",
    "cpu": "powershell -Command \"$cpu=Get-CimInstance Win32_Processor; Write-Host ('LoadPercentage='+$cpu.LoadPercentage); Write-Host '---'; Get-Process | Sort-Object CPU -Descending | Select-Object -First 5 Name,CPU | ForEach-Object {Write-Host ($_.Name+' '+$_.CPU)}\"",
    "install_path": "powershell -Command \"Get-ChildItem C:\\,D:\\ -Directory -Filter '*ShenTong*' -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 5 FullName | ForEach-Object {Write-Host $_.FullName}\"",
    "os_errors": "powershell -Command \"Get-EventLog -LogName System -EntryType Error -Newest 30 2>$null | ForEach-Object {Write-Host ($_.TimeGenerated.ToString('yyyy-MM-dd HH:mm:ss')+' '+$_.Message.Substring(0,[Math]::Min(200,$_.Message.Length)))}\"",
    "db_log_errors": "powershell -Command \"Get-ChildItem C:\\\\,D:\\\\ -Filter 'elog*' -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -First 3 | ForEach-Object { Write-Host ('===FILE:'+$_.FullName+'==='); Get-Content $_.FullName -Tail 500 -ErrorAction SilentlyContinue }\"",
}

OS_CHECK_LABELS = {
    "memory": "\u5185\u5b58\u4f7f\u7528\u60c5\u51b5",
    "disk": "\u78c1\u76d8\u4f7f\u7528\u60c5\u51b5",
    "cpu": "CPU\u8d1f\u8f7d\u60c5\u51b5",
    "install_path": "\u6570\u636e\u5e93\u5b89\u88c5\u8def\u5f84",
    "os_errors": "\u64cd\u4f5c\u7cfb\u7edf\u65e5\u5fd7\u9519\u8bef",
    "db_log_errors": "\u6570\u636e\u5e93\u65e5\u5fd7\u9519\u8bef\u6587\u4ef6",
}


def _os_checks(server_config):
    _import_collector()
    return OS_CHECKS_WIN if _is_win(server_config) else OS_CHECKS_LINUX


def collect_os_info(server_config, enabled_os_checks):
    """Run OS checks on the target server and parse results."""
    _import_collector()
    results = {}
    os_checks = _os_checks(server_config)
    cmds = [(n, os_checks[n]) for n in enabled_os_checks if n in os_checks]
    if not cmds:
        return results

    need_ssh = _need_ssh(server_config)
    use_ps = _is_win(server_config)

    # Windows-over-SSH path: execute checks one by one
    if use_ps and need_ssh:
        client = _ssh_connect(server_config)
        try:
            for check_name, cmd in cmds:
                cmd_wrapped = cmd + ' 2>&1'
                try:
                    out, err, ec = _ssh_exec(client, cmd_wrapped, timeout=30)
                    raw = out.strip()
                    if not raw and err:
                        raw = err.strip()
                    result = {"output": strip_ansi(raw), "error": "", "exit_code": ec}
                    _enrich_result(check_name, raw, result)
                    results[check_name] = result
                except Exception as e:
                    results[check_name] = {"output": "", "error": str(e), "exit_code": -1}
        finally:
            client.close()
        return results

    # Batch execution path (Linux local/SSH, Windows local)
    sep = "OSCAR_OS_SEP"
    if use_ps:
        cmds_str = ' & echo ' + sep + ' & '.join(c for _, c in cmds)
        full_cmd = 'echo ' + sep + ' & ' + cmds_str + ' 2>&1'
    else:
        qsep = shlex.quote(sep)
        cmds_str = ('; echo ' + qsep + '; ').join(c for _, c in cmds)
        full_cmd = '(' + 'echo ' + qsep + '; ' + cmds_str + ')'

    if need_ssh:
        try:
            client = _ssh_connect(server_config)
            try:
                out, err, ec = _ssh_exec(client, full_cmd, timeout=60)
            finally:
                client.close()
        except Exception as e:
            out, err, ec = "", str(e), -1
    else:
        out, err, ec = _run_local(full_cmd, timeout=60)

    blocks = out.split(sep)
    for i, (check_name, _) in enumerate(cmds):
        raw = blocks[i + 1] if i + 1 < len(blocks) else ""
        result = {"output": strip_ansi(raw).strip(), "error": "", "exit_code": 0}
        if not result["output"].strip() and err:
            result["error"] = err.strip()[:500]
        _enrich_result(check_name, raw, result)
        results[check_name] = result

    return results


def _enrich_result(check_name, raw, result):
    """Add parsed columns/rows for structured OS checks (memory, disk, cpu)."""
    _import_collector()
    if check_name not in ('memory', 'disk', 'cpu'):
        return
    parsed = parse_table_output(raw)
    if parsed:
        result['columns'] = parsed['columns']
        result['rows'] = parsed['rows']
    if check_name == 'cpu':
        if 'load average' in raw:
            m = re.search(r'load average:\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)', raw)
        else:
            m = re.search(r'LoadPercentage[= ]*(\d+)', raw)
        if m:
            result['load_1m'] = m.group(1)
            try:
                result['load_5m'] = m.group(2)
                result['load_15m'] = m.group(3)
            except IndexError:
                pass
        m2 = re.search(r'up\s+(.+?),\s+\d+\s+user', raw)
        if m2:
            result['uptime'] = m2.group(1).strip()
