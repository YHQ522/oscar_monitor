import json
import os
import sys
import threading
import random
import shlex
import subprocess
from collector import _ssh_connect, _ssh_exec

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')

DEFAULT_CONFIG = {
    "log_db": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": 2003,
        "user": "SYSDBA",
        "pass": "",
        "dbname": "OSRDB",
        "isql": "isql",
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_user": "root",
        "ssh_pass": "",
    },
    "log_enabled": False,
    "server_db_enabled": False,
    "log_retention_days": 30,
    "collect_workers": 8
}

_lock = threading.Lock()
_table_created = False


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _temp_sql():
    return f'/tmp/oscar_p_{random.randint(10000, 99999)}.sql'


def _build_sql(db_cfg, sql_file, sql):
    qt = shlex.quote(f"{db_cfg['user']}/{db_cfg['pass']}" if db_cfg.get('pass') else db_cfg['user'])
    isql = f"{db_cfg.get('isql','isql')} -h {db_cfg['host']} -p {db_cfg['port']} -d {db_cfg['dbname']} -U {qt}"
    return f"cat > {sql_file} << 'OSCAREOF'\n{sql}\nOSCAREOF\n{isql} < {sql_file} 2>&1; R=$?; rm -f {sql_file}; exit $R"


def _exec_sql(db_cfg, sql):
    sql_file = _temp_sql()
    cmd = _build_sql(db_cfg, sql_file, sql)
    ssh_host = db_cfg.get('ssh_host', '')
    try:
        if ssh_host and ssh_host not in ('127.0.0.1', 'localhost'):
            client = _ssh_connect({
                'ssh_host': ssh_host, 'ssh_port': db_cfg.get('ssh_port', 22),
                'ssh_user': db_cfg.get('ssh_user', 'root'), 'ssh_pass': db_cfg.get('ssh_pass', '')
            })
            try:
                _ssh_exec(client, cmd, timeout=15)
            finally:
                client.close()
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            if r.returncode != 0 and (r.stderr or r.stdout):
                print(f"[persist] exec failed rc={r.returncode}: {r.stderr[:200] or r.stdout[:200]}")
    except Exception as e:
        import traceback
        print(f"[persist] exec error: {e}")


LOG_TABLE = 'OSCAR_LOG_COLLECT'
REQUIRED_COLUMNS = [
    'id', 'server_name', 'check_type', 'error_msg', 'occur_time',
    'exec_user', 'exec_tool', 'exec_sql', 'cost_seconds', 'occur_count'
]


def _get_table_columns(db_cfg, table_name=None):
    if table_name is None:
        table_name = LOG_TABLE
    sql = f"select column_name from information_schema.columns where lower(table_name)='{table_name.lower()}' order by ordinal_position;"
    sql_file = _temp_sql()
    cmd = _build_sql(db_cfg, sql_file, sql)
    try:
        ssh_host = db_cfg.get('ssh_host', '')
        if ssh_host and ssh_host not in ('127.0.0.1', 'localhost'):
            client = _ssh_connect({
                'ssh_host': ssh_host, 'ssh_port': db_cfg.get('ssh_port', 22),
                'ssh_user': db_cfg.get('ssh_user', 'root'), 'ssh_pass': db_cfg.get('ssh_pass', '')
            })
            try:
                out, _, _ = _ssh_exec(client, cmd, timeout=10)
            finally:
                client.close()
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            out = r.stdout
        cols = []
        for line in out.strip().split('\n'):
            line = line.strip().lower()
            if line and line != 'column_name' and not line.startswith('---') and not line.startswith('('):
                cols.append(line)
        return cols
    except Exception:
        return None


def _ensure_table(db_cfg):
    global _table_created
    if _table_created:
        return True

    _exec_sql(db_cfg, f"""
create table if not exists {LOG_TABLE} (
    id           serial primary key,
    server_name  varchar(200),
    check_type   varchar(50),
    error_msg    text,
    occur_time   timestamp default now(),
    exec_user    varchar(100),
    exec_tool    varchar(100),
    exec_sql     text,
    cost_seconds numeric(10,3),
    occur_count  int default 1
);
""".strip())
    _table_created = True
    return True


def persist_db_error(server_name, log_entry):
    """persist a parsed database log entry"""
    cfg = load_config()
    db = cfg.get('log_db', {})
    if not cfg.get('log_enabled'):
        return
    if not log_entry.get('msg'):
        return
    with _lock:
        if not _ensure_table(db):
            return

    safe = lambda v: (v or '').replace("'", "''")[:1000]
    sname = safe(server_name)
    msg = safe(log_entry.get('msg', ''))
    euser = safe(log_entry.get('user', ''))
    etool = safe(log_entry.get('tool', ''))
    esql = safe(log_entry.get('sql', ''))
    cost = log_entry.get('cost', 0) or 0
    otime = safe(log_entry.get('time', ''))

    _exec_sql(db, f"""
insert into oscar_log_collect (server_name, check_type, error_msg, occur_time, exec_user, exec_tool, exec_sql, cost_seconds)
select '{sname}', 'db_error', '{msg}', '{otime}'::timestamp, '{euser}', '{etool}', '{esql}', {cost}
where not exists (
    select 1 from oscar_log_collect
    where server_name='{sname}' and error_msg='{msg}' and coalesce(exec_sql,'')='{esql}'
);
update oscar_log_collect set occur_count=occur_count+1
where server_name='{sname}' and error_msg='{msg}' and coalesce(exec_sql,'')='{esql}';
""")


def persist_slow_sql(server_name, sql_entry):
    """persist a slow SQL entry"""
    cfg = load_config()
    db = cfg.get('log_db', {})
    if not cfg.get('log_enabled'):
        return
    with _lock:
        if not _ensure_table(db):
            return

    safe = lambda v: (v or '').replace("'", "''")[:1000]
    sname = safe(server_name)
    msg = safe(sql_entry.get('sql', ''))[:800]
    cost = float(sql_entry.get('cost', 0) or 0)

    _exec_sql(db, f"""
insert into oscar_log_collect (server_name, check_type, error_msg, cost_seconds)
select '{sname}', 'slow_sql', '{msg}', {cost}
where not exists (
    select 1 from oscar_log_collect
    where server_name='{sname}' and check_type='slow_sql' and error_msg='{msg}'
);
update oscar_log_collect set occur_count=occur_count+1, cost_seconds={cost}
where server_name='{sname}' and check_type='slow_sql' and error_msg='{msg}';
""")


def persist_os_error(server_name, check_type, error_msg):
    cfg = load_config()
    db = cfg.get('log_db', {})
    if not db.get('enabled') or not error_msg or not error_msg.strip():
        return
    with _lock:
        if not _ensure_table(db):
            return
    safe_msg = error_msg[:500].replace("'", "''")
    safe_server = (server_name or '').replace("'", "''")
    safe_type = (check_type or '').replace("'", "''")
    _exec_sql(db, f"""
insert into oscar_log_collect (server_name, check_type, error_msg)
select '{safe_server}', '{safe_type}', '{safe_msg}'
where not exists (
    select 1 from oscar_log_collect
    where server_name='{safe_server}' and check_type='{safe_type}' and error_msg='{safe_msg}'
);
update oscar_log_collect set occur_count=occur_count+1
where server_name='{safe_server}' and check_type='{safe_type}' and error_msg='{safe_msg}';
""")


def cleanup_old_logs():
    cfg = load_config()
    db = cfg.get('log_db', {})
    if not cfg.get('log_enabled'):
        return
    days = cfg.get('log_retention_days', 30)
    with _lock:
        if not _ensure_table(db):
            return
    _exec_sql(db, f"delete from oscar_log_collect where occur_time < now() - interval '{days} days';")


def query_logs(server_name, limit=200):
    cfg = load_config()
    db = cfg.get('log_db', {})
    if not cfg.get('log_enabled'):
        return []
    if not _ensure_table(db):
        return []
    safe_server = (server_name or '').replace("'", "''")
    result = []
    sql_file = _temp_sql()
    sql = f"select check_type, error_msg, occur_count, coalesce(to_char(occur_time,'YYYY-MM-DD HH24:MI:SS'),''), coalesce(exec_user,''), coalesce(exec_tool,''), coalesce(exec_sql,''), coalesce(cost_seconds,0) from oscar_log_collect where server_name='{safe_server}' order by occur_time desc limit {limit};"
    cmd = _build_sql(db, sql_file, sql)
    try:
        ssh_host = db.get('ssh_host', '')
        if ssh_host and ssh_host not in ('127.0.0.1', 'localhost'):
            client = _ssh_connect({
                'ssh_host': ssh_host, 'ssh_port': db.get('ssh_port', 22),
                'ssh_user': db.get('ssh_user', 'root'), 'ssh_pass': db.get('ssh_pass', '')
            })
            try:
                out, err, _ = _ssh_exec(client, cmd, timeout=15)
            finally:
                client.close()
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            out = r.stdout
        for line in out.strip().split('\n'):
            line = line.strip()
            if line and '|' in line and not line.startswith(('check_type', '---', '(')):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 8:
                    result.append({
                        'type': parts[0], 'msg': parts[1], 'count': parts[2],
                        'time': parts[3], 'user': parts[4], 'tool': parts[5],
                        'sql': parts[6], 'cost': parts[7]
                    })
    except Exception:
        pass
    return result
