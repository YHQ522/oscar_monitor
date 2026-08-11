"""公共常量：OS 检查命令、标签、错误翻译表。"""
from __future__ import annotations

# ═══════════════ OS 检查命令 ═══════════════
OS_CHECKS_LINUX: dict[str, str] = {
    "memory": "free -h 2>/dev/null || cat /proc/meminfo 2>/dev/null | head -20",
    "disk": "df -h 2>/dev/null",
    "cpu": "uptime 2>/dev/null; echo '---'; top -bn1 2>/dev/null | head -10 || echo 'top not available'",
    "install_path": "find / -maxdepth 4 -type d \\( -name 'oscar' -o -name 'ShenTong' \\) 2>/dev/null | head -5",
    "os_errors": "cat /var/log/messages* 2>/dev/null | grep -i error | tail -50; echo '===FAIL==='; cat /var/log/messages* 2>/dev/null | grep -i fail | tail -50",
    "db_log_errors": "find / -maxdepth 5 -name 'elog*' -type f 2>/dev/null | head -3 | while read f; do echo \"===FILE:$f===\"; tail -500 \"$f\" 2>/dev/null; done",
}

OS_CHECKS_WIN: dict[str, str] = {
    "memory": "powershell -Command \"$os=Get-CimInstance Win32_OperatingSystem; Write-Host ('TotalMB='+[math]::Round($os.TotalVisibleMemorySize/1024)+' FreeMB='+[math]::Round($os.FreePhysicalMemory/1024)+' UsedMB='+[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1024))\"",
    "disk": "powershell -Command \"Get-PSDrive -PSProvider FileSystem | Where-Object {$_.Used -gt 0} | ForEach-Object {Write-Host ($_.Name+' '+[math]::Round($_.Used/1GB,1)+'GB/'+[math]::Round(($_.Used+$_.Free)/1GB,1)+'GB')}\"",
    "cpu": "powershell -Command \"$cpu=0;$src='snap';try{$s=Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 2 -ea stop;$cpu=[math]::Round($s.CounterSamples[-1].CookedValue);$src='avg'}catch{$s1=(Get-CimInstance Win32_Processor).LoadPercentage;sleep -m 400;$s2=(Get-CimInstance Win32_Processor).LoadPercentage;sleep -m 400;$s3=(Get-CimInstance Win32_Processor).LoadPercentage;$cpu=[math]::Round(($s1+$s2+$s3)/3)};Write-Host('LoadPercentage='+$cpu+' Source='+$src);Write-Host '---';Get-Process|Sort CPU -Descending|Select -f 5 Name,CPU|%{Write-Host($_.Name+' '+$_.CPU)}\"",
    "install_path": "powershell -Command \"Get-ChildItem C:\\,D:\\ -Directory -Filter '*ShenTong*' -Recurse -Depth 3 -ErrorAction SilentlyContinue | Select-Object -First 5 FullName | ForEach-Object {Write-Host $_.FullName}\"",
    "os_errors": "powershell -Command \"Get-EventLog -LogName System -EntryType Error -Newest 30 2>$null | ForEach-Object {Write-Host ($_.TimeGenerated.ToString('yyyy-MM-dd HH:mm:ss')+' '+$_.Message.Substring(0,[Math]::Min(200,$_.Message.Length)))}\"",
    "db_log_errors": "powershell -Command \"Get-ChildItem C:\\\\,D:\\\\ -Filter 'elog*' -Recurse -Depth 4 -ErrorAction SilentlyContinue | Select-Object -First 3 | ForEach-Object { Write-Host ('===FILE:'+$_.FullName+'==='); Get-Content $_.FullName -Tail 500 -ErrorAction SilentlyContinue }\"",
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
    "active_queries": "正在执行的SQL",
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
