"""适配器与查询集测试。"""
from __future__ import annotations

from app.adapters import all_adapters, get_adapter, get_query_sets
from app.core.db_exec import parse_isql_output, parse_table_output


def test_adapter_registry():
    assert set(all_adapters().keys()) == {"oscar", "mysql", "postgresql", "oracle"}


def test_get_adapter_aliases():
    assert get_adapter("shentong").db_type == "oscar"
    assert get_adapter("pg").db_type == "postgresql"
    assert get_adapter("unknown").db_type == "oscar"


def test_query_sets_structure():
    for db_type in ("oscar", "mysql", "postgresql", "oracle"):
        qs = get_query_sets(db_type)
        assert "basic_info" in qs
        assert "performance" in qs
        for cat, cfg in qs.items():
            assert "label" in cfg
            assert cfg["queries"]


def test_build_cli_oscar():
    server = {"db_type": "oscar", "db_host": "h", "db_port": 2003, "db_user": "u", "db_pass": "p", "db_name": "d", "isql_cmd": "isql"}
    cli = get_adapter("oscar").build_cli(server)
    assert cli.startswith("isql -h h -p 2003 -d d -U")


def test_build_cli_mysql():
    server = {"db_type": "mysql", "db_host": "h", "db_port": 3306, "db_user": "root", "db_pass": "p", "db_name": "mydb", "isql_cmd": "mysql"}
    cli = get_adapter("mysql").build_cli(server)
    assert cli == "mysql -h h -P 3306 -u root -pp mydb"


def test_build_cli_postgresql():
    server = {"db_type": "postgresql", "db_host": "h", "db_port": 5432, "db_user": "pg", "db_pass": "p", "db_name": "mydb", "isql_cmd": "psql"}
    cli = get_adapter("postgresql").build_cli(server)
    # Windows 上 shlex.quote 对简单值不加引号
    assert cli == "PGPASSWORD=p psql -h h -p 5432 -U pg -d mydb"


def test_build_cli_postgresql_win():
    server = {"db_type": "postgresql", "db_host": "h", "db_port": 5432, "db_user": "pg", "db_pass": "p", "db_name": "mydb", "isql_cmd": "psql", "os_type": "windows"}
    cli = get_adapter("postgresql").build_cli(server)
    assert cli == "set PGPASSWORD=p&& psql -h h -p 5432 -U pg -d mydb"


def test_build_cli_oracle():
    server = {"db_type": "oracle", "db_host": "h", "db_port": 1521, "db_user": "system", "db_pass": "p", "db_name": "ORCL", "isql_cmd": "sqlplus"}
    cli = get_adapter("oracle").build_cli(server)
    assert cli == "sqlplus -S system/p@h:1521/ORCL"


def test_build_cli_no_password():
    # 无密码时不应带 / 分隔
    server = {"db_type": "oscar", "db_host": "h", "db_port": 2003, "db_user": "SYSDBA", "db_pass": "", "db_name": "OSRDB", "isql_cmd": "isql"}
    cli = get_adapter("oscar").build_cli(server)
    assert cli == "isql -h h -p 2003 -d OSRDB -U SYSDBA"


def test_query_set_sizes():
    """每种数据库类型都应包含 5 个标准类别。"""
    for db_type in ("oscar", "mysql", "postgresql", "oracle"):
        qs = get_query_sets(db_type)
        assert set(qs.keys()) == {"basic_info", "db_info", "storage", "objects", "performance"}


def test_parse_isql_output():
    out = (
        "Connect to:\nusing new protocol\n\n"
        "VERSION | EXTRA\n"
        "--------+------\n"
        "5.1.2   | x\n"
        "(1 row)\n"
    )
    parsed = parse_isql_output(out, "version")
    assert parsed["columns"] == ["VERSION", "EXTRA"]
    assert parsed["rows"] == [["5.1.2", "x"]]


def test_parse_isql_single_column():
    out = "COUNT(*)\n--------\n42\n(1 row)\n"
    parsed = parse_isql_output(out, "count")
    # 无 | 分隔时返回单列「结果」；表头行及其虚线分隔行不应作为数据行
    assert parsed["columns"] == ["结果"]
    assert parsed["rows"] == [["42"]]


def test_parse_table_output():
    out = "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 100G 50G 50G 50% /"
    parsed = parse_table_output(out)
    assert parsed is not None
    assert parsed["columns"] == ["文件系统", "大小", "已用", "可用", "使用率", "挂载点"]
    assert parsed["rows"][0] == ["/dev/sda1", "100G", "50G", "50G", "50%", "/"]


def test_parse_db_log_errors_structured():
    from app.services.collector import _parse_db_log_errors_structured

    raw = (
        "===FILE:/opt/ShenTong/log/elog_20260817.txt===\n"
        "2026-08-17 10:18:30, /*Main*/ LOG, version: 251217-825.11\n"
        "2026-08-17 10:18:30, /*Main*/ NOTICE, 参数 BUF 设置为 1\n"
        "2026-08-17 10:18:31, ERROR, 连接失败: 超时\n"
        "  续行内容\n"
    )
    parsed = _parse_db_log_errors_structured(raw)
    assert parsed is not None
    assert parsed["columns"] == ["文件", "时间", "级别", "内容"]
    # 最新在前（倒序）
    assert parsed["rows"][0] == ["elog_20260817.txt", "2026-08-17 10:18:31", "ERROR", "连接失败: 超时 续行内容"]
    assert parsed["rows"][-1] == ["elog_20260817.txt", "2026-08-17 10:18:30", "LOG", "version: 251217-825.11"]


def test_parse_db_log_errors_hours_filter():
    from datetime import datetime, timedelta

    from app.services.collector import _parse_db_log_errors_structured

    old = (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")
    new = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    raw = f"===FILE:/x/elog.txt===\n{old}, ERROR, 旧错误\n{new}, ERROR, 新错误\n"
    parsed = _parse_db_log_errors_structured(raw, hours=2)
    assert parsed is not None
    # 时间窗（2h）过滤：只保留新错误
    assert len(parsed["rows"]) == 1
    assert parsed["rows"][0][3] == "新错误"


def test_resolve_svc_name():
    from app.services.collector import _resolve_svc_name

    # 留空 → oscar 自动推导 oscardb_<库名>d
    assert _resolve_svc_name({"db_name": "OSRDB"}) == "oscardb_OSRDBd"
    # 其他数据库类型留空 → 按类型推导，不套用 oscar 命名
    assert _resolve_svc_name({"db_type": "mysql", "db_name": "mydb"}) == "mysqld"
    assert _resolve_svc_name({"db_type": "postgresql", "db_name": "mydb"}) == "postgresql"
    assert _resolve_svc_name({"db_type": "oracle", "db_name": "ORCL"}) == "oracle"
    # 占位符替换
    assert _resolve_svc_name({"svc_name": "oscardb_{db_name}d", "db_name": "TEST"}) == "oscardb_TESTd"
    assert _resolve_svc_name({"svc_name": "oracle_{db_host}", "db_host": "1.2.3.4"}) == "oracle_1.2.3.4"
    # 固定名原样返回
    assert _resolve_svc_name({"svc_name": "mysvc", "db_name": "X"}) == "mysvc"
    # 未知占位符原样返回（不抛异常）
    assert _resolve_svc_name({"svc_name": "x_{unknown}"}) == "x_{unknown}"


def test_exec_sql_remote_windows_uses_stdin_pipe(monkeypatch):
    """远程 Windows 目标机：SQL 通过 stdin 管道传入 CLI，不依赖远程临时文件。"""
    from app.core import db_exec

    captured: dict = {}

    class FakeChannel:
        def shutdown_write(self) -> None:
            captured["stdin_closed"] = True

        def recv_exit_status(self) -> int:
            return 0

    class FakeStdin:
        def __init__(self):
            self.channel = FakeChannel()
            self.data = b""

        def write(self, data: bytes) -> None:
            self.data += data

    class FakeOut:
        def __init__(self):
            self.channel = FakeChannel()

        def read(self) -> bytes:
            return b""

    class FakeClient:
        def exec_command(self, cmd: str, timeout=None):
            captured["cmd"] = cmd
            return FakeStdin(), FakeOut(), FakeOut()

        def close(self) -> None:
            pass

    monkeypatch.setattr(db_exec, "ssh_connect", lambda server, timeout=15: FakeClient())
    monkeypatch.setattr(db_exec, "need_ssh", lambda server: True)

    server = {
        "db_type": "oscar", "db_host": "h", "db_port": 2003, "db_user": "u", "db_pass": "p",
        "db_name": "d", "isql_cmd": "isql", "ssh_host": "1.2.3.4", "ssh_port": 22,
        "ssh_user": "admin", "ssh_pass": "x", "os_type": "windows",
    }
    out, err, ec = db_exec.exec_sql(server, "SELECT 1;")
    assert ec == 0
    # 命令为 cmd /c 包裹的 CLI 命令，无文件重定向
    assert captured["cmd"].startswith('cmd /c "isql')
    assert "<" not in captured["cmd"]
    # 标准输入已写入 SQL 并关闭（stdin 管道方案）
    assert captured.get("stdin_closed") is True
