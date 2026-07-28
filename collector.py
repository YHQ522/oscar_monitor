import paramiko
import re
import time
import uuid
import shlex
import subprocess

QUERY_SETS = {
    "basic_info": {
        "label": "\u57fa\u7840\u4fe1\u606f",
        "queries": {
            "version": "select version();",
            "version_detail": "select versiondetail;",
            "non_default_params": "SELECT NAME, VALUE, ISDEFAULT FROM V$PARAMETER WHERE ISDEFAULT='FALSE' AND NAME NOT LIKE 'TRANSACTION ISOLATION LEVEL';",
        }
    },
    "db_info": {
        "label": "\u6570\u636e\u5e93\u4fe1\u606f",
        "queries": {
            "database_info": "SELECT * FROM V_SYS_DATABASE_INFO;",
            "ha_slave_info": "SELECT * FROM V_SYS_HA_SLAVE_INFO;",
        }
    },
    "storage": {
        "label": "\u5b58\u50a8\u7a7a\u95f4",
        "queries": {
            "effective_space": "SELECT TRUNC(SUM(SIZE)/1024/1024)||'MB' AS EFFECTIVE_SPACE FROM SYS_CLASS, V_SEGMENT_INFO WHERE RELID = OID;",
            "schema_space": "SELECT USENAME, SUM(SIZE)/1024.0/1024||'M' TOTAL_SPACE FROM SYS_CLASS, V_SEGMENT_INFO, SYS_SHADOW WHERE RELID = OID AND USESYSID = RELOWNER GROUP BY RELOWNER, USENAME;",
            "tablespace_info": "SELECT TSNAME, TSINITSIZE, TSNEXTSIZE, TSPCTFREE, TSPCTUSED, TSFILL FROM SYS_TABLESPACE;",
            "datafile_info": "SELECT A.FILEID, B.TSNAME, A.PATH, A.SIZE/1024.0/1024||'M' CURRENT_SIZE, A.FREESIZE/1024.0/1024||'M' FREESIZE, ((1-A.FREESIZE*1.0/A.SIZE)*100)||'%' PCT_USED, A.MAXSIZE MAX_SIZE, A.NEXTSIZE/1024.0/1024||'M' NEXTSIZE, A.CREATIONTIME FROM V_SYS_DATAFILE_INFO A, SYS_TABLESPACE B WHERE A.TABLESPACEID = B.TSID ORDER BY SIZE DESC;",
            "logfile_info": "SELECT * FROM V_SYS_LOGWRITE_INFO;",
            "table_disk_space": "SELECT TRUNC(SUM(B.SIZE)/1024/1024,2)||' MB' TABLE_SPACE FROM SYS_CLASS A, V_SEGMENT_INFO B WHERE RELSID = SEGID AND RELNAMESPACE != 11 AND RELKIND = 'r';",
            "index_disk_space": "SELECT TRUNC(SUM(B.SIZE)/1024/1024,2)||' MB' INDEX_SPACE FROM SYS_CLASS A, V_SEGMENT_INFO B WHERE RELSID = SEGID AND RELNAMESPACE != 11 AND RELKIND = 'i';",
        }
    },
    "objects": {
        "label": "\u6570\u636e\u5e93\u5bf9\u8c61\u7edf\u8ba1",
        "queries": {
            "table_count_total": "SELECT COUNT(*) TOTAL_TABLE_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = 'r' AND RELNAME NOT IN ('AQ$_QUEUES','AQ$_QUEUE_TABLES','DBMS_LOCK_ALLOCATED','SYS_JOBS');",
            "table_count_by_user": "SELECT ALL_USERS.USERNAME, COUNT(*) TABLE_COUNT FROM SYS_CLASS, ALL_USERS WHERE SYS_CLASS.RELOWNER=ALL_USERS.USER_ID AND RELNAMESPACE != 11 AND RELKIND = 'r' AND RELNAME NOT IN ('AQ$_QUEUES','AQ$_QUEUE_TABLES','DBMS_LOCK_ALLOCATED','SYS_JOBS') GROUP BY 1;",
            "index_count_total": "SELECT COUNT(*) TOTAL_INDEX_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = 'i' AND RELNAME NOT IN ('AQ$_QUEUES_PKEY','AQ$_QUEUE_TABLES_PKEY','DBMS_LOCK_ALLOCATED_PKEY','QUEUE_TBL_UNIQUE','QUEUE_UNIQUE','SYS_JOBS_PKEY');",
            "index_count_by_user": "SELECT ALL_USERS.USERNAME, COUNT(*) INDEX_COUNT FROM SYS_CLASS, ALL_USERS WHERE SYS_CLASS.RELOWNER=ALL_USERS.USER_ID AND RELNAMESPACE != 11 AND RELKIND = 'i' AND RELNAME NOT IN ('AQ$_QUEUES_PKEY','AQ$_QUEUE_TABLES_PKEY','DBMS_LOCK_ALLOCATED_PKEY','QUEUE_TBL_UNIQUE','QUEUE_UNIQUE','SYS_JOBS_PKEY') GROUP BY 1;",
            "view_count_total": "SELECT COUNT(*) TOTAL_VIEW_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = 'v' AND RELNAME NOT IN ('DBA_JOBS','USER_JOBS');",
            "view_count_by_user": "SELECT ALL_USERS.USERNAME, COUNT(*) VIEW_COUNT FROM SYS_CLASS, ALL_USERS WHERE SYS_CLASS.RELOWNER=ALL_USERS.USER_ID AND RELNAMESPACE != 11 AND RELKIND = 'v' AND RELNAME NOT IN ('DBA_JOBS','USER_JOBS') GROUP BY 1;",
            "proc_count_total": "SELECT COUNT(*) TOTAL_PROC_NUM FROM SYS_PROC WHERE PRONAMESPACE NOT IN (11,12) AND PRONAME NOT IN ('LT_CONCAT','WM_CONCAT');",
            "proc_count_by_user": "SELECT USERNAME, COUNT(*) PROCEDURE_COUNT FROM SYS_PROC, ALL_USERS WHERE SYS_PROC.PROOWNER=ALL_USERS.USER_ID AND PRONAMESPACE NOT IN (11,12) GROUP BY 1;",
        }
    },
    "performance": {
        "label": "\u6027\u80fd\u76d1\u63a7",
        "queries": {
            "session_count": "SELECT COUNT(*) AS CONNECTION_COUNT FROM V_SYS_SESSIONS;",
            "session_by_ip": "SELECT COUNT(*), USER_IP FROM V_SYS_SESSIONS GROUP BY USER_IP ORDER BY COUNT(*) DESC;",
            "deadlock_count": "SELECT COUNT(*) FROM V$SESSION WHERE SID IN (SELECT SID FROM V$LOCK WHERE BLOCK=1);",
            "wait_chains": "SELECT * FROM V$WAIT_CHAINS;",
            "active_queries": "SELECT \"SESSION ID\", \"CURRENT SQL\", USER_IP, \"LOGON USER\" FROM V_SYS_SESSIONS WHERE \"CURRENT SQL\" IS NOT NULL;",
            "non_auto_commit": "SELECT COUNT(*) AS NON_AUTO_COMMIT_COUNT FROM V$TRANSACTION WHERE EXPLICIT_TRANS='t';",
            "idle_non_auto_commit": "SELECT COUNT(*) AS IDLE_NON_AUTO_COMMIT FROM V$TRANSACTION VT, V$SESSION VS WHERE VT.SESSION_ID=VS.SID AND VT.EXPLICIT_TRANS='t' AND VS.CURRENT_SQL IS NULL;",
            "db_memory": "SELECT * FROM V$GLOBAL_MEMORY;",
            "slow_sql": "SELECT \"TIME(s)\", SQL FROM V_SYS_TOP_COST_SQLS WHERE \"TIME(s)\" > 0.5 AND SQL NOT LIKE 'SELECT%FROM V_SYS_TOP_COST_SQLS%' AND SQL NOT LIKE 'SELECT%FROM V_SYS_SESSIONS%' ORDER BY \"TIME(s)\" DESC LIMIT 20;",
        }
    },
}

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
    "cpu": "powershell -Command \"$cpu=0;$src='snap';try{$s=Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2 -ea stop;$cpu=[math]::Round($s.CounterSamples[-1].CookedValue);$src='avg'}catch{$s1=(Get-CimInstance Win32_Processor).LoadPercentage;sleep -m 400;$s2=(Get-CimInstance Win32_Processor).LoadPercentage;sleep -m 400;$s3=(Get-CimInstance Win32_Processor).LoadPercentage;$cpu=[math]::Round(($s1+$s2+$s3)/3)};Write-Host('LoadPercentage='+$cpu+' Source='+$src);Write-Host '---';Get-Process|Sort CPU -Descending|Select -f 5 Name,CPU|%{Write-Host($_.Name+' '+$_.CPU)}\"",
    "install_path": "powershell -Command \"Get-ChildItem C:\\,D:\\ -Directory -Filter '*ShenTong*' -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 5 FullName | ForEach-Object {Write-Host $_.FullName}\"",
    "os_errors": "powershell -Command \"Get-EventLog -LogName System -EntryType Error -Newest 30 2>$null | ForEach-Object {Write-Host ($_.TimeGenerated.ToString('yyyy-MM-dd HH:mm:ss')+' '+$_.Message.Substring(0,[Math]::Min(200,$_.Message.Length)))}\"",
    "db_log_errors": "powershell -Command \"Get-ChildItem C:\\\\,D:\\\\ -Filter 'elog*' -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -First 3 | ForEach-Object { Write-Host ('===FILE:'+$_.FullName+'==='); Get-Content $_.FullName -Tail 500 -ErrorAction SilentlyContinue }\"",
}

OS_CHECKS = OS_CHECKS_LINUX

OS_CHECK_LABELS = {
    "memory": "\u5185\u5b58\u4f7f\u7528\u60c5\u51b5",
    "disk": "\u78c1\u76d8\u4f7f\u7528\u60c5\u51b5",
    "cpu": "CPU\u8d1f\u8f7d\u60c5\u51b5",
    "install_path": "\u6570\u636e\u5e93\u5b89\u88c5\u8def\u5f84",
    "os_errors": "\u64cd\u4f5c\u7cfb\u7edf\u65e5\u5fd7\u9519\u8bef",
    "db_log_errors": "\u6570\u636e\u5e93\u65e5\u5fd7\u9519\u8bef\u6587\u4ef6",
}

QUERY_LABELS = {
    "version": "\u7248\u672c\u4fe1\u606f",
    "version_detail": "\u7248\u672c\u8be6\u7ec6\u4fe1\u606f",
    "non_default_params": "\u975e\u9ed8\u8ba4\u53c2\u6570",
    "database_info": "\u6570\u636e\u5e93\u4fe1\u606f",
    "ha_slave_info": "\u4e3b\u5907\u8282\u70b9\u4fe1\u606f",
    "effective_space": "\u6570\u636e\u5e93\u6709\u6548\u7a7a\u95f4",
    "schema_space": "\u5404\u6a21\u5f0f\u5360\u7528\u7a7a\u95f4",
    "tablespace_info": "\u8868\u7a7a\u95f4\u4fe1\u606f",
    "datafile_info": "\u6570\u636e\u6587\u4ef6\u4fe1\u606f",
    "logfile_info": "\u65e5\u5fd7\u6587\u4ef6\u4fe1\u606f",
    "table_disk_space": "\u8868\u5360\u7528\u78c1\u76d8\u7a7a\u95f4",
    "index_disk_space": "\u7d22\u5f15\u5360\u7528\u78c1\u76d8\u7a7a\u95f4",
    "table_count_total": "\u7528\u6237\u8868\u603b\u6570",
    "table_count_by_user": "\u5404\u7528\u6237\u8868\u6570",
    "index_count_total": "\u7528\u6237\u7d22\u5f15\u603b\u6570",
    "index_count_by_user": "\u5404\u7528\u6237\u7d22\u5f15\u6570",
    "view_count_total": "\u7528\u6237\u89c6\u56fe\u603b\u6570",
    "view_count_by_user": "\u5404\u7528\u6237\u89c6\u56fe\u6570",
    "proc_count_total": "\u5b58\u50a8\u8fc7\u7a0b\u603b\u6570",
    "proc_count_by_user": "\u5404\u7528\u6237\u5b58\u50a8\u8fc7\u7a0b\u6570",
    "session_count": "\u5f53\u524d\u8fde\u63a5\u6570",
    "session_by_ip": "\u6309IP\u5206\u7ec4\u8fde\u63a5",
    "deadlock_count": "\u6b7b\u9501\u6570",
    "wait_chains": "\u7b49\u5f85\u94fe\u4fe1\u606f",
    "active_queries": "\u6b63\u5728\u6267\u884c\u7684SQL",
    "non_auto_commit": "\u975e\u81ea\u52a8\u63d0\u4ea4\u8fde\u63a5",
    "idle_non_auto_commit": "\u95f2\u7f6e\u975e\u81ea\u52a8\u63d0\u4ea4\u8fde\u63a5",
    "db_memory": "\u6570\u636e\u5e93\u5185\u5b58\u4f7f\u7528",
    "slow_sql": "\u6267\u884c\u8f83\u6162\u7684SQL",
}

HEADER_TRANSLATE = {
    "total": "\u603b\u91cf", "used": "\u5df2\u7528", "free": "\u7a7a\u95f2", "shared": "\u5171\u4eab",
    "buff/cache": "\u7f13\u5b58", "available": "\u53ef\u7528",
    "filesystem": "\u6587\u4ef6\u7cfb\u7edf", "size": "\u5927\u5c0f", "avail": "\u53ef\u7528",
    "use%": "\u4f7f\u7528\u7387", "mounted": "\u6302\u8f7d\u70b9", "on": "\u6302\u8f7d\u70b9",
    "1m": "1\u5206\u949f", "5m": "5\u5206\u949f", "15m": "15\u5206\u949f", "type": "\u7c7b\u578b",
    "totalmb": "\u603b\u91cf(MB)", "freemb": "\u7a7a\u95f2(MB)", "usedmb": "\u5df2\u7528(MB)",
    "loadpercentage": "CPU\u4f7f\u7528\u7387", "name": "\u540d\u79f0",
}

SSH_ERROR_TRANSLATE = {
    "authentication failed": "SSH认证失败，用户名或密码错误",
    "permission denied": "SSH认证失败，用户名或密码错误",
    "connection refused": "SSH连接被拒绝，请检查主机和端口",
    "connection timed out": "SSH连接超时，请检查网络和防火墙",
    "timed out": "SSH连接超时，请检查网络和防火墙",
    "no route to host": "无法连接到主机，请检查IP地址",
    "name or service not known": "主机名无法解析，请检查主机地址",
    "unable to connect to port": "SSH端口无法连接",
}

SSH_FIX_WIN = {
    "unable to connect to port": "无法连接SSH端口，Windows需开启OpenSSH：设置→应用→可选功能→添加功能→搜索OpenSSH服务器→安装",
}

SSH_FIX_LINUX = {
    "unable to connect to port": "无法连接SSH端口，Linux需安装并启动：yum install openssh-server -y && systemctl start sshd",
}

DB_ERROR_TRANSLATE = {
    "password authentication failed": "数据库认证失败，用户名或密码错误",
    "login failed": "数据库登录失败，用户名或密码错误",
    "could not connect to server": "无法连接数据库服务器，请检查主机和端口",
    "connection refused": "数据库连接被拒绝，请检查主机和端口是否正确、数据库是否启动",
    "database does not exist": "数据库不存在，请检查数据库名",
    "not found": "未找到isql命令，请检查isql命令路径",
    "command not found": "未找到isql命令，请检查isql命令路径",
    "timed out": "连接超时，请检查网络和防火墙",
    "error": "数据库连接失败，请检查用户名、密码、主机端口和数据库名",
    "fail": "数据库连接失败",
    "timeout": "连接超时",
    "unixodbc - isql": "数据库连接或认证失败，请检查用户名、密码、主机端口是否正确",
}

ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text):
    return ANSI_ESCAPE.sub('', text)


def safe_decode(data):
    if isinstance(data, str):
        return data
    for enc in ('utf-8', 'gbk', 'gb18030'):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return str(data, errors='replace')


def translate_error(msg, error_map, fix_map=None):
    if not msg:
        return "未知错误"
    msg_lower = msg.lower()
    for key, chinese in error_map.items():
        if key in msg_lower:
            result = chinese
            if fix_map:
                fix = fix_map.get(key)
                if fix:
                    result += "\n修复建议: " + fix
            return result
    if msg:
        return "错误详情: " + msg[:200]
    return "未知错误"


def _need_ssh(server_config):
    host = server_config.get('ssh_host', '')
    return bool(host and host not in ('127.0.0.1', 'localhost'))


def _is_win(server_config):
    return server_config.get('os_type', 'linux') == 'windows'


def _temp_sql_path(server_config):
    uid = uuid.uuid4().hex[:8]
    return 'C:/Windows/Temp/oscar_{}.sql'.format(uid) if _is_win(server_config) else '/tmp/oscar_{}.sql'.format(uid)


def _build_sql_cmd(server_config, sql, sql_file):
    qt = shlex.quote(_db_userpass(server_config))
    isql_cmd = server_config.get('isql_cmd', 'isql')
    db_host = server_config.get('db_host', '127.0.0.1')
    db_port = server_config.get('db_port', 2003)
    db_name = server_config.get('db_name', 'OSRDB')
    isql = f"{isql_cmd} -h {db_host} -p {db_port} -d {db_name} -U {qt}"

    if _is_win(server_config):
        # Windows: 用 Python 写 SQL 文件，避免 cmd echo 的特殊字符问题
        try:
            with open(sql_file, 'w', encoding='utf-8') as f:
                f.write(sql)
        except Exception:
            pass
        return (sql, f"cmd /c \"{isql} < {sql_file} && del {sql_file}\"")
    else:
        return (sql, f"cat > {sql_file} << 'OSCAREOF'\n{sql}\nOSCAREOF\n{isql} < {sql_file} 2>&1; R=$?; rm -f {sql_file}; exit $R")


def _db_userpass(server_config):
    u = server_config.get('db_user', 'SYSDBA')
    p = server_config.get('db_pass', '')
    return f"{u}/{p}" if p else u


def _run_local(cmd, timeout=30):
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return proc.stdout, proc.stderr, proc.returncode


def _ssh_connect(server_config, timeout=10):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=server_config.get('ssh_host'),
        port=server_config.get('ssh_port', 22),
        username=server_config.get('ssh_user', 'root'),
        password=server_config.get('ssh_pass', ''),
        timeout=timeout
    )
    return client


def _ssh_exec(client, cmd, timeout=60):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = safe_decode(stdout.read())
    err = safe_decode(stderr.read())
    ec = stdout.channel.recv_exit_status()
    return out, err, ec


def _os_checks(server_config):
    return OS_CHECKS_WIN if _is_win(server_config) else OS_CHECKS_LINUX


def parse_isql_output(output, query_name):
    output = strip_ansi(output)
    lines = output.strip().split('\n')
    clean_lines = []
    skip_next = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        lower = s.lower()
        if lower == 'connect to:' or lower.startswith('connect to:'):
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        if lower.startswith('using new protocol'):
            continue
        if lower.startswith('logon database at time'):
            continue
        if lower.startswith('logout database at time'):
            continue
        if lower.startswith('sql=>'):
            continue
        if s.startswith('(') and ('row' in lower or '行' in lower):
            continue
        clean_lines.append(s)

    if not clean_lines:
        return {"query": query_name, "columns": [], "rows": [], "raw": output}

    header_line = None
    data_start = 0
    for i, line in enumerate(clean_lines):
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                header_line = parts
                data_start = i + 1
                break

    if header_line is None:
        data_rows = []
        for line in clean_lines:
            if re.match(r'^-{3,}$', line):
                continue
            data_rows.append(line)
        return {"query": query_name, "columns": ["结果"], "rows": [[l] for l in data_rows], "raw": output}

    rows = []
    for line in clean_lines[data_start:]:
        if re.match(r'^-{3,}$', line):
            continue
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
        else:
            continue
        if len(parts) >= len(header_line):
            rows.append(parts[:len(header_line)])
        elif parts:
            rows.append(parts)

    return {"query": query_name, "columns": header_line, "rows": rows, "raw": output}


def parse_table_output(output):
    output = strip_ansi(output)
    lines = output.strip().split('\n')
    headers = None
    rows = []
    for line in lines:
        parts = line.strip().split()
        if not parts:
            continue
        first = parts[0].lower().replace('/', '').replace(':', '').replace('\\', '')
        if first in ('filesystem', '文件系统', 'totalmb', 'name'):
            headers = parts
            continue
        if not headers:
            headers = parts
            continue
        if len(parts) == len(headers) + 1:
            headers = [''] + headers
        if len(parts) >= len(headers):
            rows.append(parts[:len(headers)])
        else:
            rows.append(parts + [''] * (len(headers) - len(parts)))
    if headers and rows:
        headers = [HEADER_TRANSLATE.get(h.lower(), h) for h in headers]
        return {"columns": headers, "rows": rows}
    return None


def collect_sql_queries(server_config, query_sets, enabled_categories):
    results = {}
    all_queries = []
    for cat_name in enabled_categories:
        if cat_name not in query_sets:
            continue
        for qname, sql in query_sets[cat_name]["queries"].items():
            all_queries.append((cat_name, qname, sql))
    if not all_queries:
        return results

    need_ssh = _need_ssh(server_config)
    client = None
    try:
        if need_ssh:
            client = _ssh_connect(server_config)
        for cat_name, qname, sql in all_queries:
            sql_file = _temp_sql_path(server_config)
            _, cmd = _build_sql_cmd(server_config, sql, sql_file)
            try:
                if need_ssh:
                    out, err, ec = _ssh_exec(client, cmd, timeout=120)
                else:
                    out, err, ec = _run_local(cmd, timeout=120)
            except Exception as e:
                results.setdefault(cat_name, {})[qname] = {"query": qname, "error": str(e), "columns": [], "rows": []}
                continue

            if ec != 0 and not out.strip():
                results.setdefault(cat_name, {})[qname] = {"query": qname, "error": err or "执行失败", "columns": [], "rows": []}
            else:
                results.setdefault(cat_name, {})[qname] = parse_isql_output(out, qname)
    finally:
        if client:
            client.close()
    return results


def collect_os_info(server_config, enabled_os_checks):
    results = {}
    os_checks = _os_checks(server_config)
    cmds = [(n, os_checks[n]) for n in enabled_os_checks if n in os_checks]
    if not cmds:
        return results

    need_ssh = _need_ssh(server_config)
    use_ps = _is_win(server_config)

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
                    if check_name in ('memory', 'disk', 'cpu'):
                        parsed = parse_table_output(raw)
                        if parsed:
                            result['columns'] = parsed['columns']
                            result['rows'] = parsed['rows']
                        if check_name == 'cpu':
                            m = re.search(r'LoadPercentage[= ]*(\d+)', raw)
                            if m:
                                result['load_1m'] = m.group(1)
                    results[check_name] = result
                except Exception as e:
                    results[check_name] = {"output": "", "error": str(e), "exit_code": -1}
        finally:
            client.close()
        return results

    sep = "OSCAR_OS_SEP"
    if use_ps and not need_ssh:
        # Windows本地：逐个执行PowerShell命令，避免cmd.exe &引号嵌套问题
        for check_name, cmd in cmds:
            try:
                proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                raw = proc.stdout.strip()
                if not raw and proc.stderr:
                    raw = proc.stderr.strip()
                result = {"output": strip_ansi(raw), "error": "", "exit_code": proc.returncode}
                if check_name in ('memory', 'disk', 'cpu'):
                    parsed = parse_table_output(raw)
                    if parsed:
                        result['columns'] = parsed['columns']
                        result['rows'] = parsed['rows']
                    if check_name == 'cpu':
                        m = re.search(r'LoadPercentage[= ]*(\d+)', raw)
                        if m:
                            result['load_1m'] = m.group(1)
                results[check_name] = result
            except Exception as e:
                results[check_name] = {"output": "", "error": str(e), "exit_code": -1}
        return results

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

        if check_name in ('memory', 'disk', 'cpu'):
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
        results[check_name] = result
    return results


def test_connection(server_config):
    results = {"ssh": {"ok": False, "msg": ""}, "db": {"ok": False, "msg": "", "version": ""}}
    skip_db = server_config.get('skip_db', False)

    if _need_ssh(server_config):
        fix_map = SSH_FIX_WIN if _is_win(server_config) else SSH_FIX_LINUX
        try:
            client = _ssh_connect(server_config)
            client.close()
            results["ssh"]["ok"] = True
            results["ssh"]["msg"] = "连接成功"
        except Exception as e:
            results["ssh"]["msg"] = translate_error(str(e), SSH_ERROR_TRANSLATE, fix_map)
            return results
    else:
        results["ssh"]["msg"] = "无需远程连接（本地或未配置）"
        results["ssh"]["ok"] = True

    if skip_db:
        results["db"]["ok"] = True
        results["db"]["msg"] = "跳过（未选数据库采集项）"
        return results

    db_pass = server_config.get('db_pass', '')
    if not db_pass:
        results["db"]["msg"] = "数据库密码不能为空"
        return results

    sql_file = _temp_sql_path(server_config)
    _, cmd = _build_sql_cmd(server_config, "SELECT VERSION();", sql_file)

    need_ssh = _need_ssh(server_config)
    if need_ssh:
        client = _ssh_connect(server_config)
        try:
            out, err, ec = _ssh_exec(client, cmd, timeout=30)
        finally:
            client.close()
    else:
        out, err, ec = _run_local(cmd, timeout=30)

    if ec == 0 and out.strip():
        results["db"]["ok"] = True
        results["db"]["msg"] = "数据库连接成功"
        results["db"]["version"] = out.strip().split('\n')
    else:
        error_text = (err or out or "").strip()
        results["db"]["msg"] = translate_error(error_text, DB_ERROR_TRANSLATE)
    return results


def db_control(server_config, action):
    if not _need_ssh(server_config):
        return {"ok": False, "msg": "仅支持远程SSH操作"}

    svc_name = server_config.get('svc_name', 'oscardb_OSRDBd')
    svc_mgr = server_config.get('svc_mgr', 'service')
    if _is_win(server_config):
        agent = 'oscaragentd'
        if action == 'start':
            cmd = f'sc start {agent} & sc start {svc_name}'
        elif action == 'stop':
            cmd = f'sc stop {svc_name} & sc stop {agent}'
        elif action == 'restart':
            cmd = f'sc stop {svc_name} & sc stop {agent} & sc start {agent} & sc start {svc_name}'
        else:
            cmd = f'sc query {svc_name} & sc query {agent} & tasklist /FI "IMAGENAME eq oscar.exe" 2>nul'
    elif svc_mgr == 'systemctl':
        agent = 'oscaragentd'
        m = {
            'start': f"systemctl start {agent}; systemctl start {svc_name}",
            'stop': f"systemctl stop {svc_name}; systemctl stop {agent}",
            'restart': f"systemctl stop {svc_name}; systemctl stop {agent}; systemctl start {agent}; systemctl start {svc_name}",
            'status': f"ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10",
        }
        cmd = m.get(action, m['status'])
    elif svc_mgr == 'service':
        agent = 'oscaragentd'
        m = {
            'start': f"service {agent} start; service {svc_name} start",
            'stop': f"service {svc_name} stop; service {agent} stop",
            'restart': f"service {svc_name} stop; service {agent} stop; service {agent} start; service {svc_name} start",
            'status': f"ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10",
        }
        cmd = m.get(action, m['status'])
    elif svc_mgr == 'script':
        if action == 'start':
            cmd = server_config.get('svc_start_cmd', '')
        elif action == 'stop':
            cmd = server_config.get('svc_stop_cmd', '')
        elif action == 'restart':
            stop_cmd = server_config.get('svc_stop_cmd', '')
            start_cmd = server_config.get('svc_start_cmd', '')
            cmd = f"{stop_cmd} && sleep 2 && {start_cmd}" if stop_cmd and start_cmd else ''
        else:
            cmd = f"ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10"
        if not cmd.strip():
            return {"ok": False, "action": action, "msg": "请先配置脚本命令"}
    else:
        p = svc_mgr.rstrip('/') + '/'
        agent = 'oscaragentd'
        m = {
            'start': f"{p}{agent} start; {p}{svc_name} start",
            'stop': f"{p}{svc_name} stop; {p}{agent} stop",
            'restart': f"{p}{svc_name} stop; {p}{agent} stop; {p}{agent} start; {p}{svc_name} start",
            'status': f"ps aux | grep -v grep | grep -E '[o]scar |[o]scaragent' | head -10",
        }
        cmd = m.get(action, m['status'])

    cmd += " 2>&1"
    client = _ssh_connect(server_config)
    try:
        out, err, ec = _ssh_exec(client, cmd, timeout=60)
    finally:
        client.close()

    out = strip_ansi(out)
    status_lines = [l.strip() for l in out.split('\n') if l.strip()]
    running = any(re.search(r'[/\\]oscar\b', l) and 'oscaragent' not in l.lower() for l in status_lines)

    if action == 'status':
        return {"ok": True, "action": "status", "running": running,
                "output": '\n'.join(status_lines),
                "msg": "数据库运行中" if running else "数据库未运行"}
    if ec == 0:
        return {"ok": True, "action": action, "msg": "操作成功", "output": out.strip()[:500]}
    return {"ok": False, "action": action, "msg": (err or out or "操作失败")[:300], "output": (err or out)[:500]}


def collect_apps(server_config):
    apps = server_config.get('apps', [])
    if not apps:
        return []
    results = []
    need_ssh = _need_ssh(server_config)
    is_win = _is_win(server_config)

    if is_win:
        cmd_parts = ['powershell -Command "' + '; '.join(
            f'Write-Host \\"===={a.get("name", a.get("port", ""))}====\\"; if (netstat -ano | Select-String \\":{a["port"]}\\\") {{ Write-Host \\"RUNNING\\" }} else {{ Write-Host \\"STOPPED\\" }}'
            for a in apps
        ) + '"']
        full_cmd = cmd_parts[0]
    else:
        cmd_parts = [f'echo "===={a.get("name", a.get("port", ""))}===="; ss -tlnp | grep -q ":{a["port"]} " && echo "RUNNING" || echo "STOPPED"' for a in apps]
        full_cmd = '; '.join(cmd_parts)

    try:
        if need_ssh:
            client = _ssh_connect(server_config)
            try:
                out, err, ec = _ssh_exec(client, full_cmd, timeout=30)
            finally:
                client.close()
        else:
            out, err, ec = _run_local(full_cmd, timeout=30)

        blocks = re.split(r'====(.+?)====', out)
        i = 1
        while i + 1 < len(blocks):
            app_label = blocks[i].strip()
            status_text = blocks[i + 1].strip()
            running = 'RUNNING' in status_text
            results.append({'name': app_label, 'running': running, 'status': '运行中' if running else '已停止'})
            i += 2
    except Exception as e:
        for a in apps:
            results.append({'name': a.get('name', str(a.get('port', ''))), 'running': False, 'status': '检查失败: ' + str(e)[:100]})

    return results


def app_control(server_config, app_name, action):
    if not _need_ssh(server_config):
        return {"ok": False, "msg": "仅支持远程SSH操作"}

    apps = server_config.get('apps', [])
    app = next((a for a in apps if a.get('name') == app_name), None)
    if not app:
        return {"ok": False, "msg": f"应用 {app_name} 不存在"}

    port = app.get('port')
    svc_name = app.get('svc_name', app_name)

    if action == 'status':
        status_cmd = app.get('status_cmd', '')
        if status_cmd:
            cmd = status_cmd + ' 2>&1'
        else:
            is_win = _is_win(server_config)
            if is_win:
                cmd = f'powershell -Command "if (netstat -ano | Select-String \':{port}\')) {{ Write-Host \'RUNNING\' }} else {{ Write-Host \'STOPPED\' }}"'
            else:
                cmd = f'ss -tlnp | grep -q ":{port} " && echo "RUNNING" || echo "STOPPED"'
        cmd += ' 2>&1'
        try:
            client = _ssh_connect(server_config)
            try:
                out, err, ec = _ssh_exec(client, cmd, timeout=15)
            finally:
                client.close()
        except Exception as e:
            return {"ok": False, "action": "status", "app": app_name, "msg": f"状态查询失败: {e}"}
        running = 'RUNNING' in (out or '')
        return {"ok": True, "action": "status", "app": app_name, "running": running,
                "msg": f"{app_name} 运行中" if running else f"{app_name} 已停止"}

    if action == 'start' and app.get('start_cmd'):
        cmd = app['start_cmd']
    elif action == 'stop' and app.get('stop_cmd'):
        cmd = app['stop_cmd']
    elif action == 'restart' and app.get('stop_cmd') and app.get('start_cmd'):
        cmd = app['stop_cmd'] + '; sleep 2; ' + app['start_cmd']
    else:
        svc_mgr = app.get('svc_mgr', server_config.get('svc_mgr', 'systemctl'))
        is_win = _is_win(server_config)
        if is_win:
            if action == 'restart':
                cmd = f'sc stop {svc_name} & timeout /t 2 >nul & sc start {svc_name}'
            else:
                cmd = f'sc {action} {svc_name}'
        elif svc_mgr == 'systemctl':
            cmd = f'systemctl {action} {svc_name}'
        elif svc_mgr == 'service':
            if action == 'status':
                cmd = f'service {svc_name} status'
            else:
                cmd = f'service {svc_name} {action}'
        else:
            p = svc_mgr.rstrip('/') + '/'
            cmd = f'{p}{svc_name} {action}'

    cmd = cmd.rstrip() + ' 2>&1'
    try:
        client = _ssh_connect(server_config)
        try:
            out, err, ec = _ssh_exec(client, cmd, timeout=120)
        finally:
            client.close()
    except Exception as e:
        return {"ok": False, "action": action, "app": app_name, "msg": f"操作失败: {e}"}

    if ec == 0:
        return {"ok": True, "action": action, "app": app_name, "msg": f"{app_name} {action} 成功", "output": out.strip()[:1000]}
    return {"ok": False, "action": action, "app": app_name, "msg": (err or out or "操作失败")[:500], "output": (err or out)[:1000]}


def collect_all(server_config, enabled_categories=None, enabled_os_checks=None):
    if enabled_categories is None:
        enabled_categories = list(QUERY_SETS.keys())
    if enabled_os_checks is None:
        enabled_os_checks = list(OS_CHECKS_LINUX.keys())

    return {
        "server": server_config.get("name", server_config.get("ssh_host", "unknown")),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "os_info": collect_os_info(server_config, enabled_os_checks),
        "db_queries": collect_sql_queries(server_config, QUERY_SETS, enabled_categories),
        "apps": collect_apps(server_config),
    }
