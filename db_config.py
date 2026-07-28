import json
import uuid
import threading
import logging
from persist import load_config as load_global_config, _exec_sql, _get_table_columns
from sql_helpers import (sql_str, sql_str_null, sql_int, sql_num, sql_bool, table)

_log = logging.getLogger('oscar_monitor.db_config')

_lock = threading.Lock()

SERVERS_TABLE = 'OSCAR_SERVERS'
USERS_TABLE = 'OSCAR_USERS'

SERVERS_COLUMNS = [
    'id', 'name', 'ssh_host', 'ssh_port', 'ssh_user', 'ssh_pass',
    'db_host', 'db_port', 'db_user', 'db_pass', 'db_name', 'isql_cmd',
    'auto_refresh', 'os_type', 'in_control', 'persist_enabled',
    'svc_name', 'svc_mgr', 'svc_start_cmd', 'svc_stop_cmd',
    'enabled_categories', 'enabled_os_checks', 'apps', 'created_at'
]

USERS_COLUMNS = [
    'username', 'password', 'is_admin', 'perms', 'created_at'
]


def _cfg():
    return load_global_config().get('log_db', {})


def _db_enabled():
    return load_global_config().get('server_db_enabled', False)


def _ensure_servers_table():
    db = _cfg()
    if not _db_enabled():
        return False
    tbl = table(SERVERS_TABLE)
    _exec_sql(db, f"""
create table if not exists {tbl} (
    id           varchar(20) primary key,
    name         varchar(200),
    ssh_host     varchar(200),
    ssh_port     int default 22,
    ssh_user     varchar(100),
    ssh_pass     varchar(200),
    db_host      varchar(200),
    db_port      int default 2003,
    db_user      varchar(100),
    db_pass      varchar(200),
    db_name      varchar(100),
    isql_cmd     varchar(200) default 'isql',
    auto_refresh int default 0,
    os_type      varchar(20) default 'linux',
    in_control   boolean default true,
    persist_enabled boolean default false,
    svc_name     varchar(100),
    svc_mgr      varchar(50) default 'systemctl',
    svc_start_cmd text,
    svc_stop_cmd text,
    enabled_categories text,
    enabled_os_checks  text,
    apps         text,
    created_at   timestamp default now()
);
""".strip())
    return True


def _ensure_users_table():
    db = _cfg()
    if not _db_enabled():
        return False
    tbl = table(USERS_TABLE)
    _exec_sql(db, f"""
create table if not exists {tbl} (
    username    varchar(100) primary key,
    password    varchar(200),
    is_admin    boolean default false,
    perms       text,
    created_at  timestamp default now()
);
""".strip())
    return True


def load_servers_from_db():
    db = _cfg()
    if not _db_enabled() or not _ensure_servers_table():
        return None
    try:
        tbl = table(SERVERS_TABLE)
        import persist
        sql_file = persist._temp_sql()
        cmd = persist._build_sql(db, sql_file, f"select * from {tbl} order by created_at;")
        import subprocess
        from collector import _ssh_connect, _ssh_exec
        ssh_host = db.get('ssh_host', '')
        if ssh_host and ssh_host not in ('127.0.0.1', 'localhost'):
            client = _ssh_connect({
                'ssh_host': ssh_host, 'ssh_port': db.get('ssh_port', 22),
                'ssh_user': db.get('ssh_user', 'root'), 'ssh_pass': db.get('ssh_pass', '')
            })
            try:
                out, _, _ = _ssh_exec(client, cmd, timeout=15)
            finally:
                client.close()
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
            out = r.stdout

        servers = []
        lines = [l.strip() for l in out.split('\n') if l.strip() and '|' in l and not l.startswith(('id', '---', '('))]
        for line in lines:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 3:
                continue
            s = {
                'id': parts[0], 'name': parts[1] if len(parts) > 1 else '', 'ssh_host': parts[2] if len(parts) > 2 else '',
                'ssh_port': int(parts[3]) if len(parts) > 3 and parts[3] else 22,
                'ssh_user': parts[4] if len(parts) > 4 else '', 'ssh_pass': parts[5] if len(parts) > 5 else '',
                'db_host': parts[6] if len(parts) > 6 else '', 'db_port': int(parts[7]) if len(parts) > 7 and parts[7] else 2003,
                'db_user': parts[8] if len(parts) > 8 else '', 'db_pass': parts[9] if len(parts) > 9 else '',
                'db_name': parts[10] if len(parts) > 10 else '', 'isql_cmd': parts[11] if len(parts) > 11 else 'isql',
                'auto_refresh': int(parts[12]) if len(parts) > 12 and parts[12] else 0,
                'os_type': parts[13] if len(parts) > 13 else 'linux',
                'in_control': parts[14].lower() in ('true','t','1') if len(parts) > 14 and parts[14] else True,
                'persist_enabled': parts[15].lower() in ('true','t','1') if len(parts) > 15 and parts[15] else False,
                'svc_name': parts[16] if len(parts) > 16 else '', 'svc_mgr': parts[17] if len(parts) > 17 else 'systemctl',
                'svc_start_cmd': parts[18] if len(parts) > 18 else '', 'svc_stop_cmd': parts[19] if len(parts) > 19 else '',
                'enabled_categories': json.loads(parts[20]) if len(parts) > 20 and parts[20] else [],
                'enabled_os_checks': json.loads(parts[21]) if len(parts) > 21 and parts[21] else [],
                'apps': json.loads(parts[22]) if len(parts) > 22 and parts[22] else [],
            }
            servers.append(s)
        return servers
    except Exception:
        return None


def save_server_to_db(server):
    db = _cfg()
    if not _db_enabled() or not _ensure_servers_table():
        return
    tbl = table(SERVERS_TABLE)
    cats = json.dumps(server.get('enabled_categories', []), ensure_ascii=False)
    osch = json.dumps(server.get('enabled_os_checks', []), ensure_ascii=False)
    apps = json.dumps(server.get('apps', []), ensure_ascii=False)
    values = [
        sql_str(server.get('id'), 20), sql_str(server.get('name'), 200), sql_str(server.get('ssh_host'), 200),
        sql_int(server.get('ssh_port', 22)), sql_str(server.get('ssh_user'), 100), sql_str(server.get('ssh_pass'), 200),
        sql_str(server.get('db_host'), 200), sql_int(server.get('db_port', 2003)), sql_str(server.get('db_user'), 100),
        sql_str(server.get('db_pass'), 200), sql_str(server.get('db_name'), 100), sql_str(server.get('isql_cmd', 'isql'), 200),
        sql_int(server.get('auto_refresh', 0)), sql_str(server.get('os_type', 'linux'), 20),
        sql_bool(server.get('in_control', True)), sql_bool(server.get('persist_enabled', False)),
        sql_str(server.get('svc_name'), 100), sql_str(server.get('svc_mgr', 'systemctl'), 50),
        sql_str(server.get('svc_start_cmd'), 1000), sql_str(server.get('svc_stop_cmd'), 1000),
        sql_str(cats, 5000), sql_str(osch, 5000), sql_str(apps, 5000)
    ]
    cols = "id,name,ssh_host,ssh_port,ssh_user,ssh_pass,db_host,db_port,db_user,db_pass,db_name,isql_cmd,auto_refresh,os_type,in_control,persist_enabled,svc_name,svc_mgr,svc_start_cmd,svc_stop_cmd,enabled_categories,enabled_os_checks,apps"
    vals = ', '.join(values)
    sid = sql_str(server.get('id'), 20)
    try:
        _exec_sql(db, f"delete from {tbl} where id={sid};")
        _exec_sql(db, f"insert into {tbl} ({cols}) values ({vals});")
        _log.info("saved server %s to DB", server.get('name') or server.get('id'))
    except Exception as e:
        _log.error("save server error: %s", e)


def delete_server_from_db(server_id):
    db = _cfg()
    if not _db_enabled() or not _ensure_servers_table():
        return
    tbl = table(SERVERS_TABLE)
    sid = sql_str(server_id, max_len=20)
    _exec_sql(db, f"delete from {tbl} where id={sid};")


def sync_users_to_db(users):
    db = _cfg()
    if not _db_enabled() or not _ensure_users_table():
        return
    tbl = table(USERS_TABLE)
    for u in users:
        uname = sql_str(u.get('username'), max_len=100)
        upass = sql_str(u.get('password', ''), max_len=200)
        uadmin = sql_bool(u.get('is_admin', False))
        uperms = sql_str(json.dumps(u.get('perms', []), ensure_ascii=False), max_len=2000)
        try:
            _exec_sql(db, f"delete from {tbl} where username={uname};")
            _exec_sql(db, f"insert into {tbl} (username,password,is_admin,perms) values ({uname},{upass},{uadmin},{uperms});")
        except Exception as e:
            _log.error("sync_users error for %s: %s", u.get('username'), e)
