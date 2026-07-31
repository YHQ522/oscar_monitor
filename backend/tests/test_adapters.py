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
    # 无 | 分隔时按旧版兼容返回单列「结果」
    assert parsed["columns"] == ["结果"]
    assert parsed["rows"] == [["COUNT(*)"], ["42"]]


def test_parse_table_output():
    out = "Filesystem Size Used Avail Use% Mounted on\n/dev/sda1 100G 50G 50G 50% /"
    parsed = parse_table_output(out)
    assert parsed is not None
    assert parsed["columns"] == ["文件系统", "大小", "已用", "可用", "使用率", "挂载点"]
    assert parsed["rows"][0] == ["/dev/sda1", "100G", "50G", "50G", "50%", "/"]
