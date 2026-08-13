"""PostgreSQL 数据库适配器。"""
from __future__ import annotations

from .base import DBAdapter

QUERY_SETS: dict = {
    "basic_info": {
        "label": "基础信息",
        "queries": {
            "version": "SELECT VERSION();",
            "version_detail": "SELECT current_setting('server_version') AS version_detail, current_setting('server_version_num') AS version_num;",
            "non_default_params": "SELECT name, setting FROM pg_settings WHERE source != 'default' AND name NOT LIKE 'application_name' ORDER BY name;",
        }
    },
    "db_info": {
        "label": "数据库信息",
        "queries": {
            "database_info": "SELECT datname, pg_encoding_to_char(encoding), datcollate, pg_size_pretty(pg_database_size(datname)) AS size, datconnlimit FROM pg_database WHERE datistemplate = false ORDER BY datname;",
            "ha_slave_info": "SELECT application_name, client_addr, state, sync_state, pg_wal_lsn_diff(pg_current_wal_lsn(),replay_lsn) AS replay_lag_bytes FROM pg_stat_replication;",
        }
    },
    "storage": {
        "label": "存储空间",
        "queries": {
            "effective_space": "SELECT pg_size_pretty(pg_database_size(current_database())) AS EFFECTIVE_SPACE;",
            "schema_space": "SELECT schemaname, pg_size_pretty(SUM(pg_total_relation_size(schemaname||'.'||tablename))) AS TOTAL_SPACE FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') GROUP BY schemaname ORDER BY SUM(pg_total_relation_size(schemaname||'.'||tablename)) DESC;",
            "datafile_info": "SELECT tablename, schemaname, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size, pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)-pg_relation_size(schemaname||'.'||tablename)) AS index_size FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 30;",
            "logfile_info": "SELECT name, setting FROM pg_settings WHERE name IN ('wal_segment_size','wal_keep_size','max_wal_size','min_wal_size');",
        }
    },
    "objects": {
        "label": "数据库对象统计",
        "queries": {
            "table_count_total": "SELECT COUNT(*) TOTAL_TABLE_NUM FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema');",
            "table_count_by_user": "SELECT table_schema, COUNT(*) TABLE_COUNT FROM information_schema.tables WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema') GROUP BY table_schema ORDER BY COUNT(*) DESC;",
            "index_count_total": "SELECT COUNT(*) TOTAL_INDEX_NUM FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema');",
            "view_count_total": "SELECT COUNT(*) TOTAL_VIEW_NUM FROM information_schema.views WHERE table_schema NOT IN ('pg_catalog','information_schema');",
            "proc_count_total": "SELECT COUNT(*) TOTAL_PROC_NUM FROM information_schema.routines WHERE routine_schema NOT IN ('pg_catalog','information_schema');",
        }
    },
    "performance": {
        "label": "性能监控",
        "queries": {
            "session_count": "SELECT COUNT(*) AS CONNECTION_COUNT FROM pg_stat_activity;",
            "session_by_ip": "SELECT COUNT(*) AS CNT, client_addr FROM pg_stat_activity GROUP BY client_addr ORDER BY CNT DESC;",
            "deadlock_count": "SELECT COUNT(*) AS DEADLOCK_COUNT FROM pg_stat_database WHERE deadlocks IS NOT NULL;",
            "active_queries": "SELECT pid, usename, application_name, client_addr, state, query_start, LEFT(query,200) AS query FROM pg_stat_activity WHERE state != 'idle' AND query NOT LIKE '%pg_stat_activity%' ORDER BY query_start;",
            "db_memory": "SELECT name, setting, unit, context FROM pg_settings WHERE name IN ('shared_buffers','effective_cache_size','work_mem','maintenance_work_mem','wal_buffers','autovacuum_work_mem','max_connections');",
            "slow_sql": "SELECT total_exec_time/1000 AS time_s, LEFT(query,300) AS query, calls, mean_exec_time/1000 AS avg_time_ms FROM pg_stat_statements WHERE total_exec_time/1000 > 0.5 ORDER BY total_exec_time DESC LIMIT 20;",
        }
    },
}


class PostgreSqlAdapter(DBAdapter):
    db_type = "postgresql"
    label = "PostgreSQL"
    default_port = 5432
    default_user = "postgres"
    default_db = "postgres"
    cli_tool = "psql"
    cli_heredoc = False
    cli_win_file = True
    query_sets = QUERY_SETS

    def sql_now(self) -> str:
        return "now()"

    def sql_interval(self, days: int) -> str:
        return f"now() - interval '{days} days'"

    def sql_to_char(self, col: str) -> str:
        return f"to_char({col},'YYYY-MM-DD HH24:MI:SS')"

    def sql_cast_ts(self, v: str) -> str:
        return f"'{v}'::timestamp"

    def sql_concat(self, a: str, _b: str) -> str:
        return f"coalesce({a},'')"
