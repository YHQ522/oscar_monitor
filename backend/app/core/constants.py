"""公共常量：OS 检查命令、标签、错误翻译表。"""
from __future__ import annotations

# ═══════════════ OS 检查命令 ═══════════════
OS_CHECKS_LINUX: dict[str, str] = {
    "memory": "free -h 2>/dev/null || cat /proc/meminfo 2>/dev/null | head -20",
    "disk": "df -h 2>/dev/null",
    "cpu": "uptime 2>/dev/null; echo '---'; top -bn1 2>/dev/null | head -10 || echo 'top not available'",
    "install_path": "find / -maxdepth 4 -type d \\( -name 'oscar' -o -name 'ShenTong' \\) 2>/dev/null | head -5",
    "os_errors": "cat /var/log/messages* 2>/dev/null | grep -i error | tail -50; echo '===FAIL==='; cat /var/log/messages* 2>/dev/null | grep -i fail | tail -50",
    "db_log_errors": "find / -maxdepth 5 -name 'elog*' -type f -printf '%T@ %p\\n' 2>/dev/null | sort -rn | head -3 | cut -d' ' -f2- | while read f; do echo \"===FILE:$f===\"; tail -500 \"$f\" 2>/dev/null | grep -iE 'ERROR|FATAL|PANIC|WARNING'; done",
}

OS_CHECKS_WIN: dict[str, str] = {
    "memory": "powershell -Command \"$os=Get-CimInstance Win32_OperatingSystem; Write-Host ('TotalMB='+[math]::Round($os.TotalVisibleMemorySize/1024)+' FreeMB='+[math]::Round($os.FreePhysicalMemory/1024)+' UsedMB='+[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1024))\"",
    "disk": 'powershell -Command "Get-CimInstance Win32_LogicalDisk -Filter \'DriveType=3\' | ForEach-Object {Write-Host ($_.DeviceID[0]+\' \'+[math]::Round(($_.Size-$_.FreeSpace)/1GB,1)+\'GB/\'+[math]::Round($_.Size/1GB,1)+\'GB\')}"',
    "cpu": (
        'powershell -Command "$s1=(Get-CimInstance Win32_Processor).LoadPercentage | Measure-Object -Average; '
        "$s1=[int]$s1.Average; sleep -m 300; "
        "$s2=(Get-CimInstance Win32_Processor).LoadPercentage | Measure-Object -Average; "
        "$s2=[int]$s2.Average; $cpu=[math]::Round(($s1+$s2)/2); "
        "Write-Host('LoadPercentage='+$cpu+' Source=avg'); "
        "Write-Host '---'; Get-Process|Sort CPU -Descending|Select -f 5 Name,CPU|"
        '%{Write-Host($_.Name+\' \'+$_.CPU)}"'
    ),
    "install_path": (
        'powershell -Command "$svc=Get-CimInstance Win32_Service -ErrorAction SilentlyContinue '
        "| Where-Object {$_.PathName -match 'oscar|shentong'} | Select-Object -First 5 -ExpandProperty PathName; "
        "if($svc){foreach($s in $svc){$exe=[regex]::Match($s,'.*?\\.exe').Value; "
        "if($exe){$exe=$exe.Trim([char]34); if($exe){Write-Host (Split-Path -Parent $exe)}}}}"
        "else{Get-ChildItem C:\\,D:\\ -Directory -Filter '*ShenTong*' -Recurse -Depth 2 "
        '-ErrorAction SilentlyContinue | Select-Object -First 5 -ExpandProperty FullName}"'
    ),
    "os_errors": "powershell -Command \"Get-EventLog -LogName System -EntryType Error -Newest 30 2>$null | ForEach-Object {Write-Host ($_.TimeGenerated.ToString('yyyy-MM-dd HH:mm:ss')+' '+$_.Message.Substring(0,[Math]::Min(200,$_.Message.Length)))}\"",
    "db_log_errors": "powershell -Command \"Get-ChildItem C:\\\\,D:\\\\ -Filter 'elog*' -Recurse -Depth 4 -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 3 | ForEach-Object { Write-Host ('===FILE:'+$_.FullName+'==='); Get-Content $_.FullName -Tail 500 -ErrorAction SilentlyContinue | Select-String -Pattern 'ERROR','FATAL','PANIC','WARNING' | ForEach-Object { Write-Host $_.Line } }\"",
}

OS_CHECK_LABELS: dict[str, str] = {
    "memory": "内存使用情况",
    "disk": "磁盘使用情况",
    "cpu": "CPU负载情况",
    "install_path": "数据库安装路径",
    "os_errors": "操作系统日志错误",
    "db_log_errors": "数据库日志错误文件",
}

# 依赖数据库的系统检查项：仅系统监控（skip_db）模式下应被排除
DB_RELATED_OS_CHECKS: set[str] = {"install_path", "db_log_errors"}

QUERY_LABELS: dict[str, str] = {
    "version": "版本信息",
    "version_detail": "版本详细信息",
    "non_default_params": "非默认参数",
    "database_info": "数据库信息",
    "ha_slave_info": "主备节点信息",
    "effective_space": "数据库有效空间",
    "schema_space": "各模式占用空间",
    "tablespace_info": "表空间信息",
    "datafile_info": "数据文件信息",
    "logfile_info": "日志文件信息",
    "table_disk_space": "表占用磁盘空间",
    "index_disk_space": "索引占用磁盘空间",
    "table_count_total": "用户表总数",
    "table_count_by_user": "各用户表数",
    "index_count_total": "用户索引总数",
    "index_count_by_user": "各用户索引数",
    "view_count_total": "用户视图总数",
    "view_count_by_user": "各用户视图数",
    "proc_count_total": "存储过程总数",
    "proc_count_by_user": "各用户存储过程数",
    "session_count": "当前连接数",
    "session_by_ip": "按IP分组连接",
    "deadlock_count": "死锁数",
    "wait_chains": "等待链信息",
    "active_queries": "业务会话",
    "non_auto_commit": "非自动提交连接",
    "idle_non_auto_commit": "闲置非自动提交连接",
    "db_memory": "数据库内存使用",
    "slow_sql": "执行较慢的SQL",
}

HEADER_TRANSLATE: dict[str, str] = {
    "total": "总量", "used": "已用", "free": "空闲", "shared": "共享",
    "buff/cache": "缓存", "available": "可用",
    "filesystem": "文件系统", "size": "大小", "avail": "可用",
    "use%": "使用率", "mounted": "挂载点", "on": "挂载点", "mounted on": "挂载点",
    "1m": "1分钟", "5m": "5分钟", "15m": "15分钟", "type": "类型",
    "totalmb": "总量(MB)", "freemb": "空闲(MB)", "usedmb": "已用(MB)",
    "loadpercentage": "CPU使用率", "name": "名称",
}

# ═══════════════ 查询结果列名 → 中文（键为归一化：小写、去空格/下划线） ═══════════════
COLUMN_TRANSLATE: dict[str, str] = {
    # ── 通用 ──
    "count": "数量", "cnt": "数量", "value": "值", "result": "结果",
    "fullname": "完整路径", "output": "输出",
    # ── 版本 / 参数 ──
    "version": "版本号", "versiondetail": "版本详细信息", "versiondetail2": "版本详细信息",
    "versiondetailnum": "版本号", "banner": "版本信息",
    "isdefault": "是否默认值", "name": "参数名称",
    "variablename": "变量名称", "variablevalue": "变量值",
    "setting": "设置值", "unit": "单位", "context": "上下文",
    # ── 数据库信息 ──
    "dbname": "数据库名", "dbuser": "数据库用户", "dbport": "端口", "dbid": "数据库ID",
    "charset": "字符集", "collation": "排序规则", "dbsize": "数据库大小",
    "datname": "数据库名", "pgencodingtochar": "字符集", "datcollate": "排序规则",
    "size": "大小", "datconnlimit": "连接数限制",
    "schemaname": "数据库名", "defaultcharactersetname": "默认字符集",
    "defaultcollationname": "默认排序规则",
    "created": "创建时间", "logmode": "日志模式", "openmode": "打开模式",
    "databaserole": "数据库角色", "flashbackon": "闪回开关", "forcelogging": "强制日志",
    "protectionmode": "保护模式", "protectionlevel": "保护级别",
    "applicationname": "应用名称", "clientaddr": "客户端地址", "syncstate": "同步状态",
    "replaylagbytes": "回放延迟(字节)", "syncmode": "同步模式",
    "flushlsn": "刷新LSN", "replaylsn": "回放LSN",
    "slaveip": "备库IP", "slaveport": "备库端口",
    "curlsn": "当前LSN", "curlfile": "当前日志文件", "curlsize": "当前日志大小",
    # ── 存储空间 ──
    "effectivespace": "有效空间", "totalspace": "总占用空间",
    "tablespace": "表占用空间", "indexspace": "索引占用空间",
    "usename": "用户名", "username": "用户名", "owner": "所有者", "user": "用户",
    "tsname": "表空间名", "tsinitsize": "初始大小", "tsnextsize": "扩展大小",
    "tspctfree": "空闲百分比", "tspctused": "已用百分比", "tsfill": "填充因子",
    "fileid": "文件编号", "path": "路径", "filename": "文件名",
    "currentsize": "当前大小", "freesize": "空闲大小", "pctused": "使用率",
    "maxsize": "最大大小", "nextsize": "扩展大小", "creationtime": "创建时间",
    "realsize": "实际大小", "initsize": "初始大小",
    "scaleextend": "自动扩展", "usageratio": "使用率", "isactive": "状态",
    "sizemb": "大小(MB)", "datamb": "数据大小(MB)", "indexmb": "索引大小(MB)",
    "minmb": "最小(MB)", "maxmb": "最大(MB)",
    "tablespacename": "表空间名",
    "tablename": "表名", "tablerows": "数据行数", "totalsize": "总大小",
    "tablesize": "表大小", "indexsize": "索引大小",
    "logfilesizemb": "日志文件大小(MB)", "logfilesingroup": "日志文件组数",
    "group#": "日志组号", "thread#": "线程号", "sequence#": "序列号",
    "members": "成员数", "autoextensible": "自动扩展",
    # ── 对象统计 ──
    "totaltablenum": "表总数", "tablecount": "表数量",
    "totalindexnum": "索引总数", "indexcount": "索引数量",
    "totalviewnum": "视图总数", "viewcount": "视图数量",
    "totalprocnum": "存储过程总数", "procedurecount": "存储过程数量",
    # ── 性能监控 ──
    "connectioncount": "当前连接数", "sessioncount": "会话数",
    "userip": "客户端IP", "host": "主机", "machine": "机器",
    "sessionid": "会话ID", "currentsql": "当前执行的SQL", "currentuser": "当前用户",
    "appname": "应用", "lastsql": "最近执行的SQL", "logontime": "登录时间",
    "chainid": "等待链ID", "pid": "进程ID", "txnid": "事务ID", "serial": "序列号",
    "serial#": "序列号", "blockerisvalid": "阻塞者有效", "blockerpid": "阻塞者PID",
    "blockersessionid": "阻塞者会话ID", "blockerserial": "阻塞者序列号",
    "blockertxnid": "阻塞者事务ID", "inwait": "是否等待",
    "timesincelastwait": "距上次等待时间(秒)", "waitid": "等待ID",
    "waitevent": "等待事件", "p1": "参数1", "p1text": "参数1描述",
    "p2": "参数2", "p2text": "参数2描述", "p3": "参数3", "p3text": "参数3描述",
    "p4": "参数4", "p4text": "参数4描述", "inwaitsecs": "等待秒数",
    "numwaiters": "等待者数量",
    "nonautocommitcount": "非自动提交连接数", "idlenonautocommit": "空闲非自动提交数",
    "deadlockcount": "死锁数", "activetransactions": "活动事务数",
    "memoryname": "内存名称", "memorysize": "内存大小",
    "component": "组件", "state": "状态", "status": "状态",
    "time(s)": "耗时(秒)", "times": "耗时(秒)", "sql": "SQL语句", "sqltext": "SQL语句",
    "query": "查询语句", "querystart": "查询开始时间",
    "calls": "执行次数", "avgtimesms": "平均耗时(ms)",
    "id": "连接ID", "db": "数据库", "command": "命令", "info": "当前语句",
    "sid": "会话ID", "sqlid": "SQL ID", "lastcallet": "活动秒数",
    "block": "是否阻塞",
    # ── OS 检查（Windows/Linux 输出列）──
    "total": "总量", "used": "已用", "free": "空闲", "shared": "共享",
    "buff/cache": "缓存", "available": "可用",
    "filesystem": "文件系统", "avail": "可用", "use%": "使用率",
    "mounted": "挂载点", "on": "挂载点", "mountedon": "挂载点",
    "1m": "1分钟", "5m": "5分钟", "15m": "15分钟", "type": "类型",
    "totalmb": "总量(MB)", "freemb": "空闲(MB)", "usedmb": "已用(MB)",
    "loadpercentage": "CPU使用率",
}


def _normalize_col(name: object) -> str:
    """列名归一化：小写并去除空格与下划线。"""
    return str(name).lower().replace(" ", "").replace("_", "")


def translate_column(name: object) -> str:
    """单个列名 → 中文（查不到保留原名）。"""
    raw = str(name)
    zh = COLUMN_TRANSLATE.get(_normalize_col(raw))
    return zh if zh else raw


def translate_columns(cols) -> list[str]:
    """列名列表 → 中文列表。"""
    return [translate_column(c) for c in (cols or [])]

# ═══════════════ 错误翻译 ═══════════════
SSH_ERROR_TRANSLATE: dict[str, str] = {
    "authentication failed": "SSH认证失败，用户名或密码错误",
    "permission denied": "SSH认证失败，用户名或密码错误",
    "connection refused": "SSH连接被拒绝，请检查主机和端口",
    "connection timed out": "SSH连接超时，请检查网络和防火墙",
    "timed out": "SSH连接超时，请检查网络和防火墙",
    "no route to host": "无法连接到主机，请检查IP地址",
    "name or service not known": "主机名无法解析，请检查主机地址",
    "unable to connect to port": "SSH端口无法连接",
}

SSH_FIX_WIN: dict[str, str] = {
    "unable to connect to port": "无法连接SSH端口，Windows需开启OpenSSH：设置→应用→可选功能→添加功能→搜索OpenSSH服务器→安装",
}

SSH_FIX_LINUX: dict[str, str] = {
    "unable to connect to port": "无法连接SSH端口，Linux需安装并启动：yum install openssh-server -y && systemctl start sshd",
}

DB_ERROR_TRANSLATE: dict[str, str] = {
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
