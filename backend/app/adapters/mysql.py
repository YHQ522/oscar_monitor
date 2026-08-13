"""MySQL 数据库适配器。"""
from __future__ import annotations

from .base import DBAdapter

QUERY_SETS: dict = {
    "basic_info": {
        "label": "基础信息",
        "queries": {
            "version": "SELECT VERSION();",
            "version_detail": "SHOW VARIABLES LIKE 'version_comment';",
            "non_default_params": "SELECT VARIABLE_NAME, VARIABLE_VALUE FROM performance_schema.global_variables WHERE VARIABLE_NAME IN ('max_connections','innodb_buffer_pool_size','innodb_log_file_size','innodb_flush_log_at_trx_commit','sync_binlog','query_cache_size','tmp_table_size','max_heap_table_size','thread_cache_size','table_open_cache','innodb_io_capacity');",
        }
    },
    "db_info": {
        "label": "数据库信息",
        "queries": {
            "database_info": "SELECT SCHEMA_NAME, DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME NOT IN ('information_schema','mysql','performance_schema','sys') ORDER BY SCHEMA_NAME;",
            "ha_slave_info": "SHOW SLAVE STATUS\\G",
        }
    },
    "storage": {
        "label": "存储空间",
        "queries": {
            "effective_space": "SELECT CONCAT(ROUND(SUM(data_length+index_length)/1024/1024,2),' MB') AS EFFECTIVE_SPACE FROM information_schema.tables;",
            "schema_space": "SELECT TABLE_SCHEMA, CONCAT(ROUND(SUM(data_length+index_length)/1024/1024,2),' M') TOTAL_SPACE FROM information_schema.tables WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') GROUP BY TABLE_SCHEMA ORDER BY SUM(data_length+index_length) DESC;",
            "datafile_info": "SELECT TABLE_NAME, TABLE_ROWS, ROUND((data_length+index_length)/1024/1024,2) AS SIZE_MB, ROUND(data_length/1024/1024,2) AS DATA_MB, ROUND(index_length/1024/1024,2) AS INDEX_MB FROM information_schema.tables WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') ORDER BY (data_length+index_length) DESC LIMIT 30;",
            "logfile_info": "SELECT @@innodb_log_file_size/1024/1024 AS LOG_FILE_SIZE_MB, @@innodb_log_files_in_group AS LOG_FILES_IN_GROUP;",
        }
    },
    "objects": {
        "label": "数据库对象统计",
        "queries": {
            "table_count_total": "SELECT COUNT(*) TOTAL_TABLE_NUM FROM information_schema.tables WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys');",
            "table_count_by_user": "SELECT TABLE_SCHEMA, COUNT(*) TABLE_COUNT FROM information_schema.tables WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys') GROUP BY TABLE_SCHEMA ORDER BY COUNT(*) DESC;",
            "index_count_total": "SELECT COUNT(*) TOTAL_INDEX_NUM FROM information_schema.statistics WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys');",
            "view_count_total": "SELECT COUNT(*) TOTAL_VIEW_NUM FROM information_schema.views WHERE TABLE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys');",
            "proc_count_total": "SELECT COUNT(*) TOTAL_PROC_NUM FROM information_schema.routines WHERE ROUTINE_SCHEMA NOT IN ('information_schema','mysql','performance_schema','sys');",
        }
    },
    "performance": {
        "label": "性能监控",
        "queries": {
            "session_count": "SELECT COUNT(*) AS CONNECTION_COUNT FROM information_schema.PROCESSLIST;",
            "session_by_ip": "SELECT COUNT(*) AS CNT, HOST FROM information_schema.PROCESSLIST GROUP BY HOST ORDER BY CNT DESC LIMIT 30;",
            "deadlock_count": "SHOW ENGINE INNODB STATUS\\G",
            "active_queries": "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, LEFT(INFO,200) AS INFO FROM information_schema.PROCESSLIST WHERE COMMAND != 'Sleep' AND INFO IS NOT NULL ORDER BY TIME DESC;",
            "db_memory": "SELECT VARIABLE_NAME, VARIABLE_VALUE FROM performance_schema.global_status WHERE VARIABLE_NAME IN ('Innodb_buffer_pool_reads','Innodb_buffer_pool_read_requests','Innodb_buffer_pool_pages_total','Innodb_buffer_pool_pages_free','Innodb_buffer_pool_pages_dirty','Threads_connected','Threads_running','Innodb_rows_deleted','Innodb_rows_inserted','Innodb_rows_read','Innodb_rows_updated','Bytes_received','Bytes_sent','Qcache_hits','Qcache_inserts','Slow_queries');",
            "slow_sql": "SELECT TIME/1000 AS TIME_S, SQL_TEXT FROM mysql.slow_log WHERE TIME/1000 > 0.5 ORDER BY TIME DESC LIMIT 20;",
        }
    },
}


class MySqlAdapter(DBAdapter):
    db_type = "mysql"
    label = "MySQL"
    default_port = 3306
    default_user = "root"
    default_db = "mysql"
    cli_tool = "mysql"
    cli_heredoc = False
    cli_win_file = True
    query_sets = QUERY_SETS

    def sql_now(self) -> str:
        return "now()"

    def sql_interval(self, days: int) -> str:
        return f"date_sub(now(), interval {days} day)"

    def sql_to_char(self, col: str) -> str:
        return f"date_format({col},'%Y-%m-%d %H:%i:%s')"

    def sql_cast_ts(self, v: str) -> str:
        return f"str_to_date('{v}','%Y-%m-%d %H:%i:%s')"

    def sql_concat(self, a: str, _b: str) -> str:
        return f"ifnull({a},'')"
