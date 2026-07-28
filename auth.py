import os
import sys
import json
import time
import hashlib
import secrets
import subprocess
from collector import _ssh_connect, _ssh_exec
from persist import load_config as persist_load_config, _temp_sql, _build_sql
from db_config import sync_users_to_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), 'data')
USER_FILE = os.path.join(DATA_DIR, 'users.json')

PERMISSIONS = {
    "dashboard": "全局监控",
    "servers_view": "服务管理(查看)",
    "servers_edit": "服务管理(编辑)",
    "control_view": "启停管控(查看)",
    "control_exec": "启停管控(执行)",
    "admin": "系统管理",
}

ALL_PERMS = list(PERMISSIONS.keys())

PBKDF2_ITERATIONS = 100000
PBKDF2_PREFIX = 'pbkdf2:'


def _hash(pwd):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', pwd.encode(), salt, PBKDF2_ITERATIONS)
    return PBKDF2_PREFIX + salt.hex() + ':' + dk.hex()


def _verify(stored, password):
    if not stored:
        return False
    if stored.startswith(PBKDF2_PREFIX):
        try:
            _, salt_hex, hash_hex = stored.split(':')
            salt = bytes.fromhex(salt_hex)
            dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PBKDF2_ITERATIONS)
            return dk.hex() == hash_hex
        except (ValueError, IndexError):
            return False
    return stored == hashlib.sha256(password.encode()).hexdigest()


def _needs_upgrade(stored):
    return bool(stored) and not stored.startswith(PBKDF2_PREFIX)


_users_cache = None
_users_cache_time = 0
_migrated = False


def load_users():
    global _users_cache, _users_cache_time, _migrated
    if _users_cache is not None and time.time() - _users_cache_time < 60:
        return _users_cache
    if not os.path.exists(USER_FILE):
        default = [{
            "username": "admin",
            "password": _hash("admin123"),
            "is_admin": True,
            "perms": ALL_PERMS,
        }]
        save_users(default)
        _users_cache = default
        _users_cache_time = time.time()
        _migrated = True
        return default
    users = _load_json()
    if not _migrated:
        _migrate(users)
    if not _db_has_users():
        _sync_to_db(users)
    _users_cache = users
    return users


def _migrate(users):
    global _migrated
    changed = False
    for u in users:
        if u.get('is_admin') and set(u.get('perms', [])) != set(ALL_PERMS):
            u['perms'] = ALL_PERMS
            changed = True
        perms = u.get('perms', [])
        if 'servers' in perms:
            perms = [p for p in perms if p != 'servers']
            if 'servers_view' not in perms:
                perms.append('servers_view')
            if 'servers_edit' not in perms:
                perms.append('servers_edit')
            u['perms'] = perms
            changed = True
        if 'control' in perms:
            perms = [p for p in perms if p != 'control']
            if 'control_view' not in perms:
                perms.append('control_view')
            if 'control_exec' not in perms:
                perms.append('control_exec')
            u['perms'] = perms
            changed = True
        if 'detail' in perms:
            perms = [p for p in perms if p != 'detail']
            u['perms'] = perms
            changed = True
    if changed:
        save_users(users)
    _migrated = True


def _load_json():
    with open(USER_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_users(users):
    global _users_cache, _users_cache_time
    _users_cache = users
    _users_cache_time = time.time()
    os.makedirs(os.path.dirname(USER_FILE), exist_ok=True)
    with open(USER_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    _sync_to_db(users)


def check_login(username, password):
    users = load_users()
    for u in users:
        if u.get('username') == username and _verify(u.get('password', ''), password):
            if _needs_upgrade(u.get('password', '')):
                u['password'] = _hash(password)
                save_users(users)
            return u
    return None


def change_password(username, old_pwd, new_pwd):
    if not new_pwd or len(new_pwd) < 4:
        return False, "新密码至少 4 位"
    users = load_users()
    for u in users:
        if u.get('username') == username:
            if not _verify(u.get('password', ''), old_pwd):
                return False, "原密码错误"
            u['password'] = _hash(new_pwd)
            save_users(users)
            return True, "密码修改成功"
    return False, "用户不存在"


def add_user(username, password, is_admin=False, perms=None):
    if not username or not username.strip():
        return False, "用户名不能为空"
    users = load_users()
    if any(u['username'] == username for u in users):
        return False, "用户已存在"
    users.append({
        "username": username.strip(),
        "password": _hash(password) if password else _hash("123456"),
        "is_admin": False,
        "perms": list(perms or []),
    })
    save_users(users)
    return True, "添加成功"


def update_user(username, data):
    if username == 'admin' and 'is_admin' in data:
        pass
    users = load_users()
    for u in users:
        if u.get('username') == username:
            if 'password' in data and data['password']:
                u['password'] = _hash(data['password'])
            if 'perms' in data:
                u['perms'] = list(data['perms'])
            save_users(users)
            return True, "修改成功"
    return False, "用户不存在"


def delete_user(username):
    if username == 'admin':
        return False, "不能删除 admin"
    users = load_users()
    users = [u for u in users if u.get('username') != username]
    save_users(users)
    return True, "删除成功"


def has_permission(user, perm):
    if not user:
        return False
    if user.get('is_admin'):
        return True
    return perm in user.get('perms', [])


def _sync_to_db(users):
    try:
        sync_users_to_db(users)
    except Exception:
        pass


def _db_has_users():
    try:
        cfg = persist_load_config()
        if not cfg.get('server_db_enabled'):
            return False
        db = cfg.get('log_db', {})
        sql_file = _temp_sql()
        cmd = _build_sql(db, sql_file, "select count(*) from OSCAR_USERS;")
        ssh_host = db.get('ssh_host', '')
        if ssh_host and ssh_host not in ('127.0.0.1', 'localhost'):
            client = _ssh_connect({'ssh_host': ssh_host, 'ssh_port': db.get('ssh_port', 22),
                                    'ssh_user': db.get('ssh_user', 'root'), 'ssh_pass': db.get('ssh_pass', '')})
            try:
                out, _, _ = _ssh_exec(client, cmd, timeout=10)
            finally:
                client.close()
        else:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            out = r.stdout
        for line in out.strip().split('\n'):
            parts = line.strip().split('|')
            for p in parts:
                n = p.strip()
                if n.isdigit() and int(n) > 0:
                    return True
    except Exception:
        pass
    return False
