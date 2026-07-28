import os
import sys
import json
import threading
import time
import logging
from collections import deque
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, session, request, jsonify, redirect, url_for

from auth import has_permission

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
_log = logging.getLogger('oscar_monitor')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), 'data')
    BASE_DIR = sys._MEIPASS

START_TIME = time.time()

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.config['SECRET_KEY'] = os.environ.get('OSCAR_SECRET_KEY', os.urandom(24).hex())
app.config['JSON_AS_ASCII'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 1800

# ── Rate limiter (in-memory, auto-cleanup every 5 min) ────
_LOGIN_ATTEMPTS = {}  # {ip: [(ts1, ts2, ...)]}
_RATE_LOCK = threading.Lock()
_MAX_FAILURES = 5
_BLOCK_SECONDS = 900  # 15 min
_FAIL_WINDOW = 300    # 5 min sliding window


def _check_rate_limit(ip):
    now = time.time()
    with _RATE_LOCK:
        attempts = _LOGIN_ATTEMPTS.get(ip, [])
        # prune old entries
        attempts = [t for t in attempts if now - t < _FAIL_WINDOW]
        _LOGIN_ATTEMPTS[ip] = attempts
        if len(attempts) >= _MAX_FAILURES:
            oldest = min(attempts)
            if now - oldest < _BLOCK_SECONDS:
                return False, f"登录失败次数过多，请{int((_BLOCK_SECONDS - (now - oldest)) / 60)}分钟后再试"
            # block expired, reset
            _LOGIN_ATTEMPTS[ip] = []
        return True, None


def _record_login_failure(ip):
    with _RATE_LOCK:
        _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


# periodic cleanup of stale rate-limit entries (every 10 min, daemon)
def _cleanup_rate_limits():
    while True:
        time.sleep(600)
        now = time.time()
        with _RATE_LOCK:
            stale = [ip for ip, ts_list in _LOGIN_ATTEMPTS.items()
                     if all(now - t > _BLOCK_SECONDS for t in ts_list)]
            for ip in stale:
                del _LOGIN_ATTEMPTS[ip]


threading.Thread(target=_cleanup_rate_limits, daemon=True).start()

# ── Audit log (append-only JSON lines, max 10k lines) ─────
AUDIT_FILE = os.path.join(DATA_DIR, 'audit.jsonl')
_AUDIT_LOCK = threading.Lock()
_AUDIT_MAX = 10000


def audit_log(action, detail, username=''):
    """Write an audit entry. Auto-trims old entries if > _AUDIT_MAX lines."""
    entry = {"time": time.strftime('%Y-%m-%d %H:%M:%S'), "user": username or "system",
             "action": action, "detail": str(detail)[:500], "ip": request.remote_addr if request else ''}
    with _AUDIT_LOCK:
        try:
            with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            # trim if too large (lazy, only on write)
            if os.path.getsize(AUDIT_FILE) > _AUDIT_MAX * 200:
                lines = []
                with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                if len(lines) > _AUDIT_MAX:
                    with open(AUDIT_FILE, 'w', encoding='utf-8') as f:
                        f.writelines(lines[-_AUDIT_MAX:])
        except Exception:
            pass  # audit failure must not break app


# ── Trend history (ring buffer, max 60 points = 30 min) ───
_TREND_HISTORY = {}  # {server_id: deque(maxlen=60)}
_TREND_LOCK = threading.Lock()


def _record_trend(server_id, data):
    """Store one data point per server, max 60 points."""
    point = {"ts": time.strftime('%H:%M:%S'),
             "sessions": _safe_int(data, 'db_queries.performance.session_count'),
             "deadlocks": _safe_int(data, 'db_queries.performance.deadlock_count'),
             "cpu": _safe_cpu(data),
             "mem_pct": _safe_mem(data)}
    with _TREND_LOCK:
        if server_id not in _TREND_HISTORY:
            _TREND_HISTORY[server_id] = deque(maxlen=60)
        _TREND_HISTORY[server_id].append(point)


def _safe_int(data, path):
    try:
        for key in path.split('.'):
            data = data.get(key, {})
        return int(data.get('rows', [[0]])[0][0]) if data else 0
    except Exception:
        return 0


def _safe_cpu(data):
    try:
        raw = data.get('os_info', {}).get('cpu', {}).get('output', '')
        m = __import__('re').search(r'LoadPercentage[= ]*(\d+)', raw)
        if m: return int(m.group(1))
        m = __import__('re').search(r'load average:\s*([\d.]+)', raw)
        if m: return float(m.group(1))
    except Exception:
        pass
    return None


def _safe_mem(data):
    try:
        raw = data.get('os_info', {}).get('memory', {}).get('output', '')
        m = __import__('re').search(r'TotalMB=(\d+).*?FreeMB=(\d+).*?UsedMB=(\d+)', raw)
        if m:
            total, used = int(m.group(1)), int(m.group(3))
            return round(used / total * 100, 1) if total > 0 else None
        m = __import__('re').search(r'Mem:\s+(\S+)\s+(\S+)\s+(\S+)', raw)
        if m:
            return None  # linux free -h outputs human-readable, skip for trend
    except Exception:
        pass
    return None

# ── Webhook alert (fire-and-forget, no queue) ─────────────
_WEBHOOK_EXECUTOR = None


def _get_webhook_executor():
    global _WEBHOOK_EXECUTOR
    if _WEBHOOK_EXECUTOR is None:
        _WEBHOOK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='webhook')
    return _WEBHOOK_EXECUTOR


def send_alert(server_name, alert_type, message):
    """Fire-and-forget webhook alert (non-blocking)."""
    cfg = load_config()
    url = cfg.get('webhook_url', '')
    if not url:
        return
    payload = {"msgtype": "text", "text": {"content": f"[{alert_type}] {server_name}\n{message}"}}
    _get_webhook_executor().submit(_do_webhook, url, payload)


def _do_webhook(url, payload):
    try:
        import urllib.request
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # webhook failure is non-critical

scheduler = None
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.start()
except Exception:
    _log.warning('APScheduler not available; auto-collect disabled')

_collect_executor = None

def _get_executor():
    global _collect_executor
    if _collect_executor is None:
        cfg = load_config()
        workers = max(1, min(50, cfg.get('collect_workers', 8)))
        _collect_executor = ThreadPoolExecutor(max_workers=workers)
    return _collect_executor

def _reinit_executor():
    global _collect_executor
    if _collect_executor:
        _collect_executor.shutdown(wait=False)
    _collect_executor = None

from collector import (collect_all, test_connection, db_control, app_control,
                       QUERY_SETS, QUERY_LABELS, OS_CHECKS, OS_CHECK_LABELS)
from collector import (_ssh_connect, translate_error,
                       SSH_ERROR_TRANSLATE, SSH_FIX_LINUX)
from persist import (load_config, save_config,
                     persist_os_error, persist_db_error, persist_slow_sql,
                     cleanup_old_logs, query_logs)
from db_config import load_servers_from_db, save_server_to_db, delete_server_from_db

CONFIG_FILE = os.path.join(DATA_DIR, 'servers.json')
CONFIG_LOCK = threading.Lock()

CACHE = {}
CACHE_LOCK = threading.Lock()

def load_servers():
    db_servers = load_servers_from_db()
    if db_servers is not None and len(db_servers) > 0:
        return db_servers
    with CONFIG_LOCK:
        if not os.path.exists(CONFIG_FILE):
            return []
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            servers = json.load(f)
    for s in servers:
        s.setdefault('enabled_categories', list(QUERY_SETS.keys()))
        s.setdefault('enabled_os_checks', list(OS_CHECKS.keys()))
        s.setdefault('in_control', True)
        s.setdefault('apps', [])
        s.setdefault('persist_enabled', False)
    if db_servers is not None and len(db_servers) == 0 and len(servers) > 0:
        save_servers(servers)
    return servers

def save_servers(servers):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with CONFIG_LOCK:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(servers, f, ensure_ascii=False, indent=2)
    for s in servers:
        save_server_to_db(s)

def get_server_by_id(server_id):
    for s in load_servers():
        if s.get('id') == server_id:
            return s
    return None

_SENSITIVE_KEYS = ('ssh_pass', 'db_pass')

def safe_server(s):
    return {k: v for k, v in s.items() if k not in _SENSITIVE_KEYS}

def safe_servers_list(servers):
    return [safe_server(s) for s in servers]

def template_context():
    user = session.get('user', {})
    return {
        'username': session.get('username'),
        'is_admin': user.get('is_admin', False),
        'user_perms': user.get('perms', []),
    }

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            if request.path.startswith('/api/'):
                return jsonify({'error': '未登录或会话已过期', 'redirect': url_for('login')}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def permission_required(perm):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not has_permission(session.get('user', {}), perm):
                if request.path.startswith('/api/'):
                    return jsonify({'error': '无权限'}), 403
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def any_permission_required(*perms):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = session.get('user', {})
            if user.get('is_admin'):
                return f(*args, **kwargs)
            if not any(p in user.get('perms', []) for p in perms):
                if request.path.startswith('/api/'):
                    return jsonify({'error': '无权限'}), 403
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def _persist_errors(server, result):
    if not server.get('persist_enabled'):
        return
    t = threading.Thread(target=_do_persist, args=(server, result), daemon=True)
    t.start()

def _do_persist(server, result):
    server_name = server.get('name') or server.get('ssh_host', '')
    if result.get('os_info'):
        for ck, cr in result['os_info'].items():
            text = cr.get('output', '')
            if not text:
                continue
            if ck == 'os_errors':
                for line in text.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('==='):
                        persist_os_error(server_name, ck, line)
            elif ck == 'db_log_errors':
                _parse_elog_content(server_name, text)
    perf = result.get('db_queries', {}).get('performance', {})
    slow = perf.get('slow_sql', {})
    if slow and slow.get('rows'):
        for row in slow['rows']:
            if row and len(row) >= 2:
                cost = float(row[0]) if row[0] else 0
                sql = str(row[1] or '')[:800]
                if cost >= 0.5 and sql:
                    persist_slow_sql(server_name, {'cost': cost, 'sql': sql})

def _parse_elog_content(server_name, text):
    import re
    blocks = text.split('===FILE:')
    for block in blocks:
        if not block.strip():
            continue
        lines = block.split('\n')
        filepath = lines[0].replace('===', '').strip() if lines else ''
        entry = {}
        for line in lines[1:]:
            line = line.strip()
            if not line:
                if entry and entry.get('msg'):
                    entry['tool'] = filepath.split('/')[-1][:100] if filepath else ''
                    persist_db_error(server_name, entry)
                    entry = {}
                continue
            msg_match = re.match(r'^(ERROR|FATAL|WARNING|PANIC)\s*[:\-]?\s*(.+)', line, re.IGNORECASE)
            if msg_match:
                if entry and entry.get('msg'):
                    entry['tool'] = filepath.split('/')[-1][:100] if filepath else ''
                    persist_db_error(server_name, entry)
                entry = {'msg': msg_match.group(2)[:500]}
                continue
            t_match = re.search(r'(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})', line)
            if t_match and not entry.get('time'):
                entry['time'] = t_match.group(1)
            u_match = re.search(r'(?:user|USER|User)\s*[=:]\s*(\w+)', line)
            if u_match and not entry.get('user'):
                entry['user'] = u_match.group(1)
            cost_match = re.search(r'(?:duration|cost|elapsed|耗时)\s*[=:]\s*([\d.]+)\s*(ms|s|秒|毫秒)?', line, re.IGNORECASE)
            if cost_match:
                cost = float(cost_match.group(1))
                if cost_match.group(2) in ('ms', '毫秒'):
                    cost = cost / 1000
                entry['cost'] = round(cost, 3)
            sql_match = re.search(r'(?:statement|sql|query|SQL|语句)\s*[=:]\s*(.+)', line, re.IGNORECASE)
            if sql_match and not entry.get('sql'):
                entry['sql'] = sql_match.group(1)[:800]
            if not entry.get('msg'):
                entry['msg'] = line[:500]
        if entry and entry.get('msg'):
            entry['tool'] = filepath.split('/')[-1][:100] if filepath else ''
            persist_db_error(server_name, entry)

from routes import register_routes

register_routes(app, {
    'load_servers': load_servers, 'save_servers': save_servers,
    'get_server_by_id': get_server_by_id, 'safe_server': safe_server,
    'safe_servers_list': safe_servers_list, 'template_context': template_context,
    'login_required': login_required, 'permission_required': permission_required,
    'any_permission_required': any_permission_required,
    'CACHE': CACHE, 'CACHE_LOCK': CACHE_LOCK,
    '_reinit_executor': _reinit_executor, '_persist_errors': _persist_errors,
    'collect_all': collect_all, 'test_connection': test_connection,
    'db_control': db_control, 'app_control': app_control,
    'QUERY_SETS': QUERY_SETS, 'QUERY_LABELS': QUERY_LABELS,
    'OS_CHECKS': OS_CHECKS, 'OS_CHECK_LABELS': OS_CHECK_LABELS,
    'load_config': load_config, 'save_config': save_config,
    'query_logs': query_logs, 'delete_server_from_db': delete_server_from_db,
    '_ssh_connect': _ssh_connect, 'translate_error': translate_error,
    'SSH_ERROR_TRANSLATE': SSH_ERROR_TRANSLATE, 'SSH_FIX_LINUX': SSH_FIX_LINUX,
    # new features
    'START_TIME': START_TIME, 'audit_log': audit_log,
    '_check_rate_limit': _check_rate_limit, '_record_login_failure': _record_login_failure,
    '_TREND_HISTORY': _TREND_HISTORY, '_TREND_LOCK': _TREND_LOCK,
    '_record_trend': _record_trend, 'send_alert': send_alert,
    'AUDIT_FILE': AUDIT_FILE, 'AUDIT_MAX': AUDIT_FILE,
})

def auto_collect_job():
    servers = load_servers()
    futures = []
    for server in servers:
        sid = server.get('id')
        with CACHE_LOCK:
            cached = CACHE.get(sid)
        if cached and time.time() - cached.get('time', 0) < 30:
            continue
        futures.append(_get_executor().submit(_collect_one, server))
    for f in as_completed(futures):
        try: f.result()
        except Exception: pass

def _collect_one(server):
    sid = server.get('id')
    result = collect_all(server, server.get('enabled_categories'), server.get('enabled_os_checks'))
    with CACHE_LOCK:
        CACHE[sid] = {'data': result, 'time': time.time()}
    _persist_errors(server, result)
    _record_trend(sid, result)
    # alert on critical conditions (non-blocking)
    _check_alerts(server, result)
    return result


def _check_alerts(server, result):
    """Check for critical conditions and fire webhook alerts."""
    sname = server.get('name') or server.get('ssh_host', '')
    alerts = []
    try:
        dl = result.get('db_queries', {}).get('performance', {}).get('deadlock_count', {})
        if dl and dl.get('rows') and int(dl['rows'][0][0]) > 0:
            alerts.append(f"死锁数: {dl['rows'][0][0]}")
    except Exception:
        pass
    try:
        raw = result.get('os_info', {}).get('disk', {}).get('output', '')
        for line in raw.split('\n'):
            parts = line.strip().split()
            for p in parts:
                if p.endswith('%'):
                    v = float(p[:-1])
                    if v > 90:
                        alerts.append(f"磁盘使用率: {v}%")
                    break
    except Exception:
        pass
    if alerts:
        send_alert(sname, '告警', '; '.join(alerts))

if scheduler is not None:
    scheduler.add_job(auto_collect_job, 'interval', seconds=30)
    scheduler.add_job(cleanup_old_logs, 'interval', hours=24)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='管控平台')
    parser.add_argument('--port', type=int, default=5080, help='监听端口 (默认: 5080)')
    args = parser.parse_args()
    if getattr(sys, 'frozen', False):
        import webbrowser
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(f'http://localhost:{args.port}')), daemon=True).start()
    _log.info('Starting oscar_monitor on port %d', args.port)
    app.run(host='0.0.0.0', port=args.port, debug=False)
