"""Route handlers for the oscar monitor Flask application."""
import json
import uuid
import time
import threading
import traceback
from flask import render_template, request, jsonify, redirect, url_for, session, Response

from auth import (check_login, change_password, add_user, update_user, delete_user,
                  load_users as load_auth_users, has_permission, PERMISSIONS)


def register_routes(app, ctx):
    """Register all Flask routes. `ctx` is a dict with shared state and helpers."""
    load_servers = ctx['load_servers']
    save_servers = ctx['save_servers']
    get_server_by_id = ctx['get_server_by_id']
    safe_server = ctx['safe_server']
    safe_servers_list = ctx['safe_servers_list']
    template_context = ctx['template_context']
    login_required = ctx['login_required']
    permission_required = ctx['permission_required']
    any_permission_required = ctx['any_permission_required']
    CACHE = ctx['CACHE']
    CACHE_LOCK = ctx['CACHE_LOCK']
    _reinit_executor = ctx['_reinit_executor']
    _persist_errors = ctx['_persist_errors']
    collect_all = ctx['collect_all']
    test_connection = ctx['test_connection']
    db_control = ctx['db_control']
    app_control = ctx['app_control']
    QUERY_SETS = ctx['QUERY_SETS']
    QUERY_LABELS = ctx['QUERY_LABELS']
    OS_CHECKS = ctx['OS_CHECKS']
    OS_CHECK_LABELS = ctx['OS_CHECK_LABELS']
    load_config = ctx['load_config']
    save_config = ctx['save_config']
    query_logs = ctx['query_logs']
    delete_server_from_db = ctx['delete_server_from_db']
    _ssh_connect = ctx['_ssh_connect']
    translate_error = ctx['translate_error']
    SSH_ERROR_TRANSLATE = ctx['SSH_ERROR_TRANSLATE']
    SSH_FIX_LINUX = ctx['SSH_FIX_LINUX']
    # new features (safe get with defaults)
    START_TIME = ctx.get('START_TIME', time.time())
    audit_log = ctx.get('audit_log', lambda *a, **k: None)
    _check_rate_limit = ctx.get('_check_rate_limit', lambda ip: (True, None))
    _record_login_failure = ctx.get('_record_login_failure', lambda ip: None)
    _record_trend = ctx.get('_record_trend', lambda sid, data: None)
    send_alert = ctx.get('send_alert', lambda *a: None)
    _TREND_HISTORY = ctx.get('_TREND_HISTORY', {})
    _TREND_LOCK = ctx.get('_TREND_LOCK', threading.Lock())
    AUDIT_FILE = ctx.get('AUDIT_FILE', '')

    # ── Health check (no auth) ───────────────────────────

    @app.route('/api/health')
    def api_health():
        uptime = int(time.time() - START_TIME)
        servers = load_servers()
        with CACHE_LOCK:
            online = sum(1 for sid, c in CACHE.items() if c.get('data'))
        return jsonify({
            "status": "ok", "uptime_seconds": uptime,
            "servers_total": len(servers), "servers_cached": online,
            "scheduler": "running",
        })

    # ── Auth routes ──────────────────────────────────────

    @app.route('/api/reset-password', methods=['POST'])
    def api_reset_password():
        data = request.get_json(silent=True) or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        if not username or not password:
            return jsonify({"ok": False, "msg": "用户名和密码不能为空"})
        if len(password) < 4:
            return jsonify({"ok": False, "msg": "新密码至少 4 位"})
        if username == 'admin':
            return jsonify({"ok": False, "msg": "admin 不支持此方式重置，请登录后修改"})
        from auth import load_users, save_users, _hash
        users = load_users()
        user = next((u for u in users if u.get('username') == username), None)
        if not user:
            return jsonify({"ok": False, "msg": "用户不存在"})
        if user.get('is_admin'):
            return jsonify({"ok": False, "msg": "管理员不支持此方式重置，请登录后修改"})
        user['password'] = _hash(password)
        save_users(users)
        return jsonify({"ok": True, "msg": "密码重置成功，请返回登录"})

    @app.before_request
    def refresh_session_user():
        if session.get('logged_in') and session.get('username'):
            if request.path == '/api/stream':
                return
            now = time.time()
            last = session.get('last_activity', now)
            if now - last > 1800:
                session.clear()
                if request.path.startswith('/api/'):
                    return jsonify({"error": "会话已过期", "redirect": url_for('login')}), 401
                return redirect(url_for('login'))
            session['last_activity'] = now
            user = session.get('user', {})
            if not user.get('perms') or 'servers' in user.get('perms', []) or 'control' in user.get('perms', []):
                try:
                    current = next((u for u in load_auth_users() if u.get('username') == session.get('username')), None)
                    if current:
                        session['user'] = current
                except Exception:
                    pass

    @app.errorhandler(500)
    def internal_error(e):
        tb = traceback.format_exc()
        return f"<h2>500 内部错误</h2><pre>{tb}</pre>", 500

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')
            ip = request.remote_addr or '127.0.0.1'
            allowed, block_msg = _check_rate_limit(ip)
            if not allowed:
                audit_log('login_blocked', f"user={username}", username)
                return render_template('login.html', error=block_msg)
            user = check_login(username, password)
            if user:
                session['logged_in'] = True
                session['username'] = username
                session['user'] = user
                session['last_activity'] = time.time()
                session.permanent = True
                audit_log('login', 'success', username)
                return redirect(url_for('index'))
            _record_login_failure(ip)
            audit_log('login_failed', f"user={username}", username)
            return render_template('login.html', error='用户名或密码错误')
        return render_template('login.html', error=None)

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    # ── Page routes ─────────────────────────────────────

    @app.route('/help')
    @login_required
    def help_page():
        return render_template('help.html', **template_context())

    @app.route('/')
    @login_required
    @permission_required('dashboard')
    def index():
        servers = load_servers()
        return render_template('index.html', servers=servers, servers_safe=safe_servers_list(servers), **template_context())

    @app.route('/servers')
    @login_required
    @any_permission_required('servers_view', 'servers_edit')
    def servers_page():
        servers = load_servers()
        return render_template('servers.html', servers=servers, servers_safe=safe_servers_list(servers),
                               query_sets=QUERY_SETS, os_check_labels=OS_CHECK_LABELS, **template_context())

    @app.route('/servers/add')
    @login_required
    @permission_required('servers_edit')
    def servers_add():
        return render_template('servers_add.html', query_sets=QUERY_SETS,
                               os_check_labels=OS_CHECK_LABELS, **template_context())

    @app.route('/server/<server_id>')
    @login_required
    @any_permission_required('servers_view', 'servers_edit')
    def server_detail(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return redirect(url_for('servers_page'))
        return render_template('detail.html', server=server, query_sets=QUERY_SETS,
                               os_check_labels=OS_CHECK_LABELS, query_labels=QUERY_LABELS, **template_context())

    @app.route('/control')
    @login_required
    @any_permission_required('control_view', 'control_exec')
    def control_page():
        servers = load_servers()
        return render_template('control.html', servers=servers, servers_safe=safe_servers_list(servers), **template_context())

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        if request.method == 'POST':
            username = session.get('username')
            old_pwd = request.form.get('old_password', '')
            new_pwd = request.form.get('new_password', '')
            ok, msg = change_password(username, old_pwd, new_pwd)
            return render_template('profile.html', msg=msg, ok=ok, **template_context())
        return render_template('profile.html', msg=None, ok=None, **template_context())

    @app.route('/users')
    @login_required
    @permission_required('admin')
    def users_page():
        users = load_auth_users()
        return render_template('users.html', users=users, permissions=PERMISSIONS, **template_context())

    @app.route('/config')
    @login_required
    @permission_required('admin')
    def config_page():
        return render_template('config.html', config=load_config(), **template_context())

    @app.route('/server/<server_id>/log-history')
    @login_required
    def log_history_page(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return "服务不存在", 404
        return render_template('log_history.html', server=server, **template_context())

    # ── User API routes ─────────────────────────────────

    @app.route('/api/users', methods=['POST'])
    @login_required
    @permission_required('admin')
    def api_add_user():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "无效数据"}), 400
        ok, msg = add_user(data.get('username', ''), data.get('password', ''),
                           data.get('is_admin', False), data.get('perms', []))
        return jsonify({"status": "ok" if ok else "error", "msg": msg})

    @app.route('/api/users/<username>', methods=['PUT'])
    @login_required
    @permission_required('admin')
    def api_update_user(username):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "无效数据"}), 400
        ok, msg = update_user(username, data)
        return jsonify({"status": "ok" if ok else "error", "msg": msg})

    @app.route('/api/users/<username>', methods=['DELETE'])
    @login_required
    @permission_required('admin')
    def api_delete_user(username):
        ok, msg = delete_user(username)
        return jsonify({"status": "ok" if ok else "error", "msg": msg})

    # ── Server CRUD API routes ──────────────────────────

    @app.route('/api/test-connection', methods=['POST'])
    @login_required
    def api_test_connection():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
        try:
            result = test_connection(data)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/servers', methods=['GET'])
    @login_required
    def api_list_servers():
        servers = load_servers()
        return jsonify([safe_server(s) for s in servers])

    @app.route('/api/servers/<server_id>/full', methods=['GET'])
    @login_required
    @any_permission_required('servers_view', 'servers_edit')
    def api_get_server_full(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        return jsonify(server)

    @app.route('/api/servers', methods=['POST'])
    @login_required
    @permission_required('servers_edit')
    def api_add_server():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
        servers = load_servers()
        data['id'] = uuid.uuid4().hex[:8]
        if 'enabled_categories' not in data:
            data['enabled_categories'] = list(QUERY_SETS.keys())
        if 'enabled_os_checks' not in data:
            data['enabled_os_checks'] = list(OS_CHECKS.keys())
        data['auto_refresh'] = data.get('auto_refresh', 0)
        servers.append(data)
        save_servers(servers)
        return jsonify({"status": "ok", "id": data['id']})

    @app.route('/api/servers/<server_id>', methods=['PUT'])
    @login_required
    @permission_required('servers_edit')
    def api_update_server(server_id):
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
        servers = load_servers()
        UPDATE_KEYS = ['name', 'ssh_host', 'ssh_port', 'ssh_user', 'ssh_pass',
                       'db_host', 'db_port', 'db_user', 'db_pass', 'db_name',
                       'isql_cmd', 'enabled_categories', 'enabled_os_checks', 'auto_refresh',
                       'svc_name', 'svc_mgr', 'os_type', 'in_control', 'apps',
                       'svc_start_cmd', 'svc_stop_cmd', 'persist_enabled']
        for s in servers:
            if s.get('id') == server_id:
                for key in UPDATE_KEYS:
                    if key in data:
                        s[key] = data[key]
                save_servers(servers)
                return jsonify({"status": "ok"})
        return jsonify({"error": "服务不存在"}), 404

    @app.route('/api/servers/<server_id>', methods=['DELETE'])
    @login_required
    @permission_required('servers_edit')
    def api_delete_server(server_id):
        servers = load_servers()
        servers = [s for s in servers if s.get('id') != server_id]
        save_servers(servers)
        audit_log('server_delete', f"id={server_id}", session.get('username', ''))
        delete_server_from_db(server_id)
        with CACHE_LOCK:
            CACHE.pop(server_id, None)
        return jsonify({"status": "ok"})

    # ── Data collection API routes ──────────────────────

    @app.route('/api/servers/<server_id>/collect', methods=['POST'])
    @login_required
    def api_collect(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        try:
            result = collect_all(server, server.get('enabled_categories'), server.get('enabled_os_checks'))
            with CACHE_LOCK:
                CACHE[server_id] = {"data": result, "time": time.time()}
            _persist_errors(server, result)
            _record_trend(server_id, result)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    @app.route('/api/servers/<server_id>/data', methods=['GET'])
    @login_required
    def api_get_cached(server_id):
        with CACHE_LOCK:
            cached = CACHE.get(server_id)
        if cached:
            return jsonify(cached["data"])
        return jsonify(None)

    @app.route('/api/servers/<server_id>/collect-partial', methods=['POST'])
    @login_required
    def api_collect_partial(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        data = request.get_json(silent=True) or {}
        categories = data.get('categories', [])
        os_checks = data.get('os_checks', [])
        if not categories and not os_checks:
            return jsonify({"error": "请指定采集类别"}), 400
        try:
            result = collect_all(server, categories or [], os_checks or [])
            with CACHE_LOCK:
                existing = CACHE.get(server_id, {"data": {}, "time": 0})
                existing_data = existing.get("data", {})
                if "os_info" in result:
                    existing_data["os_info"] = result["os_info"]
                if "db_queries" in result:
                    existing_data["db_queries"] = result["db_queries"]
                existing_data["server"] = result["server"]
                existing_data["timestamp"] = result["timestamp"]
                CACHE[server_id] = {"data": existing_data, "time": time.time()}
            _persist_errors(server, result)
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

    # ── Control API routes ──────────────────────────────

    @app.route('/api/servers/<server_id>/db-control', methods=['POST'])
    @login_required
    @any_permission_required('control_view', 'control_exec')
    def api_db_control(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        data = request.get_json(silent=True) or {}
        action = data.get('action', 'status')
        if action not in ('start', 'stop', 'restart', 'status'):
            return jsonify({"error": "无效的操作"}), 400
        if action != 'status':
            if not has_permission(session.get('user', {}), 'control_exec'):
                return jsonify({"error": "无执行权限"}), 403
        try:
            result = db_control(server, action)
            return jsonify(result)
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)}), 500

    @app.route('/api/servers/<server_id>/app-control', methods=['POST'])
    @login_required
    @any_permission_required('control_view', 'control_exec')
    def api_app_control(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        data = request.get_json(silent=True) or {}
        action = data.get('action', 'status')
        app_name = data.get('app')
        if action not in ('start', 'stop', 'restart', 'status'):
            return jsonify({"error": "无效的操作"}), 400
        if not app_name:
            return jsonify({"error": "请指定应用名称"}), 400
        if action != 'status':
            if not has_permission(session.get('user', {}), 'control_exec'):
                return jsonify({"error": "无执行权限"}), 403
        try:
            result = app_control(server, app_name, action)
            return jsonify(result)
        except Exception as e:
            return jsonify({"ok": False, "msg": str(e)}), 500

    # ── Config API routes ───────────────────────────────

    @app.route('/api/config', methods=['GET'])
    @login_required
    @permission_required('admin')
    def api_get_config():
        return jsonify(load_config())

    @app.route('/api/config', methods=['PUT'])
    @login_required
    @permission_required('admin')
    def api_update_config():
        data = request.get_json(silent=True) or {}
        cfg = load_config()
        for k in ('log_db', 'log_retention_days', 'collect_workers', 'log_enabled', 'server_db_enabled', 'webhook_url'):
            if k in data:
                cfg[k] = data[k]
        if 'collect_workers' in data:
            cfg['collect_workers'] = int(data['collect_workers'])
        save_config(cfg)
        _reinit_executor()
        import auth
        auth._users_cache = None
        auth.load_users()
        return jsonify({"status": "ok"})

    @app.route('/api/config/test-log-db', methods=['POST'])
    @login_required
    @permission_required('admin')
    def api_test_log_db():
        data = request.get_json(silent=True) or {}
        result = {"ssh": None, "db": None}
        ssh_host = data.get('ssh_host', '')

        if ssh_host and ssh_host not in ('127.0.0.1', 'localhost'):
            try:
                client = _ssh_connect({
                    'ssh_host': ssh_host, 'ssh_port': data.get('ssh_port', 22),
                    'ssh_user': data.get('ssh_user', 'root'), 'ssh_pass': data.get('ssh_pass', '')
                })
                client.close()
                result['ssh'] = {"ok": True, "msg": "SSH连接成功"}
            except Exception as e:
                result['ssh'] = {"ok": False, "msg": translate_error(str(e), SSH_ERROR_TRANSLATE, SSH_FIX_LINUX)}
                return jsonify(result)

        try:
            import persist
            persist._exec_sql({
                'host': data.get('host', '127.0.0.1'), 'port': data.get('port', 2003),
                'user': data.get('user', 'SYSDBA'), 'pass': data.get('pass', ''),
                'dbname': data.get('dbname', 'OSRDB'), 'isql': data.get('isql', 'isql'),
                'ssh_host': data.get('ssh_host', ''), 'ssh_port': data.get('ssh_port', 22),
                'ssh_user': data.get('ssh_user', 'root'), 'ssh_pass': data.get('ssh_pass', ''),
            }, "select 1;")
            result['db'] = {"ok": True, "msg": "数据库连接成功"}
        except Exception as e:
            result['db'] = {"ok": False, "msg": str(e)[:200]}
        return jsonify(result)

    # ── Log & Stream routes ─────────────────────────────

    @app.route('/api/servers/<server_id>/log-errors', methods=['GET'])
    @login_required
    def api_log_errors(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        server_name = server.get('name') or server.get('ssh_host', '')
        page = request.args.get('page', 1, type=int)
        size = request.args.get('size', 50, type=int)
        kw = request.args.get('kw', '')
        log_type = request.args.get('type', '')
        all_logs = query_logs(server_name, limit=5000)
        if kw:
            kw_lower = kw.lower()
            all_logs = [l for l in all_logs if kw_lower in (l.get('msg', '') + l.get('sql', '') + l.get('user', '')).lower()]
        if log_type:
            all_logs = [l for l in all_logs if l.get('type') == log_type]
        total = len(all_logs)
        start = (page - 1) * size
        paged = all_logs[start:start + size]
        return jsonify({"logs": paged, "total": total, "server": server_name})

    @app.route('/api/stream')
    @login_required
    def api_stream():
        def generate():
            last_seen = {}
            while True:
                servers = load_servers()
                updates = {}
                for s in servers:
                    sid = s.get('id')
                    with CACHE_LOCK:
                        cached = CACHE.get(sid, {}).get('data')
                    if cached:
                        ts = cached.get('timestamp', '')
                        if ts != last_seen.get(sid):
                            last_seen[sid] = ts
                            updates[sid] = cached
                if updates:
                    yield f"data: {json.dumps(updates, ensure_ascii=False)}\n\n"
                time.sleep(2)

        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no',
        })

    # ── Trend data API ──────────────────────────────────

    @app.route('/api/trends/<server_id>', methods=['GET'])
    @login_required
    def api_trends(server_id):
        with _TREND_LOCK:
            points = list(_TREND_HISTORY.get(server_id, []))
        return jsonify(points)

    # ── Audit log API ───────────────────────────────────

    @app.route('/api/audit', methods=['GET'])
    @login_required
    @permission_required('admin')
    def api_audit():
        page = request.args.get('page', 1, type=int)
        size = request.args.get('size', 50, type=int)
        try:
            with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            entries = [json.loads(l) for l in lines if l.strip()]
            entries.reverse()
            total = len(entries)
            start = (page - 1) * size
            return jsonify({"entries": entries[start:start + size], "total": total})
        except Exception:
            return jsonify({"entries": [], "total": 0})

    # ── Export API ──────────────────────────────────────

    @app.route('/api/servers/<server_id>/export', methods=['POST'])
    @login_required
    def api_export(server_id):
        server = get_server_by_id(server_id)
        if not server:
            return jsonify({"error": "服务不存在"}), 404
        try:
            result = collect_all(server, server.get('enabled_categories'), server.get('enabled_os_checks'))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["\u7c7b\u522b", "\u67e5\u8be2", "\u5217\u540d", "\u6570\u636e"])
        if result.get('db_queries'):
            for cat, queries in result['db_queries'].items():
                for qname, qr in queries.items():
                    if qr.get('columns') and qr.get('rows'):
                        writer.writerow([cat, qname, '|'.join(qr['columns']), ''])
                        for row in qr['rows']:
                            writer.writerow(['', '', '', '|'.join(str(c) for c in row)])
        if result.get('os_info'):
            for ck, cr in result['os_info'].items():
                writer.writerow(['OS', ck, '', cr.get('output', '')[:5000]])
        csv_data = output.getvalue()
        output.close()

        from flask import make_response
        resp = make_response(csv_data)
        resp.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
        resp.headers['Content-Disposition'] = f'attachment; filename={server_id}_export.csv'
        return resp
