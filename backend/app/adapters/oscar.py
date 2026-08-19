"""Oscar（神通）数据库适配器。"""
from __future__ import annotations

from .base import DBAdapter

QUERY_SETS: dict = {
    "basic_info": {
        "label": "基础信息",
        "queries": {
            "version": "select version();",
            "version_detail": "select versiondetail;",
            "non_default_params": "SELECT NAME, VALUE, ISDEFAULT FROM V$PARAMETER WHERE ISDEFAULT='FALSE' AND NAME NOT LIKE 'TRANSACTION ISOLATION LEVEL';",
        }
    },
    "db_info": {
        "label": "数据库信息",
        "queries": {
            "database_info": "SELECT * FROM V_SYS_DATABASE_INFO;",
            "ha_slave_info": "SELECT * FROM V_SYS_HA_SLAVE_INFO;",
        }
    },
    "storage": {
        "label": "存储空间",
        "queries": {
            "effective_space": "SELECT TRUNC(SUM(SIZE)/1024/1024)||'MB' AS EFFECTIVE_SPACE FROM SYS_CLASS, V_SEGMENT_INFO WHERE RELID = OID;",
            "schema_space": "SELECT USENAME, SUM(SIZE)/1024.0/1024||'M' TOTAL_SPACE FROM SYS_CLASS, V_SEGMENT_INFO, SYS_SHADOW WHERE RELID = OID AND USESYSID = RELOWNER GROUP BY RELOWNER, USENAME;",
            "tablespace_info": "SELECT TSNAME, TSINITSIZE, TSNEXTSIZE, TSPCTFREE, TSPCTUSED, TSFILL FROM SYS_TABLESPACE;",
            "datafile_info": "SELECT A.FILEID, B.TSNAME, A.PATH, A.SIZE/1024.0/1024||'M' CURRENT_SIZE, A.FREESIZE/1024.0/1024||'M' FREESIZE, ((1-A.FREESIZE*1.0/A.SIZE)*100)||'%' PCT_USED, A.MAXSIZE MAX_SIZE, A.NEXTSIZE/1024.0/1024||'M' NEXTSIZE, A.CREATIONTIME FROM V_SYS_DATAFILE_INFO A, SYS_TABLESPACE B WHERE A.TABLESPACEID = B.TSID ORDER BY SIZE DESC;",
            "logfile_info": "SELECT * FROM V_SYS_LOGFILE_INFO;",
            "table_disk_space": "SELECT TRUNC(SUM(B.SIZE)/1024/1024,2)||' MB' TABLE_SPACE FROM SYS_CLASS A, V_SEGMENT_INFO B WHERE RELSID = SEGID AND RELNAMESPACE != 11 AND RELKIND = 'r';",
            "index_disk_space": "SELECT TRUNC(SUM(B.SIZE)/1024/1024,2)||' MB' INDEX_SPACE FROM SYS_CLASS A, V_SEGMENT_INFO B WHERE RELSID = SEGID AND RELNAMESPACE != 11 AND RELKIND = 'i';",
        }
    },
    "objects": {
        "label": "数据库对象统计",
        "queries": {
            "table_count_total": "SELECT COUNT(*) TOTAL_TABLE_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = 'r' AND RELNAME NOT IN ('AQ$_QUEUES','AQ$_QUEUE_TABLES','DBMS_LOCK_ALLOCATED','SYS_JOBS');",
            "table_count_by_user": "SELECT ALL_USERS.USERNAME, COUNT(*) TABLE_COUNT FROM SYS_CLASS, ALL_USERS WHERE SYS_CLASS.RELOWNER=ALL_USERS.USER_ID AND RELNAMESPACE != 11 AND RELKIND = 'r' AND RELNAME NOT IN ('AQ$_QUEUES','AQ$_QUEUE_TABLES','DBMS_LOCK_ALLOCATED','SYS_JOBS') GROUP BY 1;",
            "index_count_total": "SELECT COUNT(*) TOTAL_INDEX_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = 'i' AND RELNAME NOT IN ('AQ$_QUEUES_PKEY','AQ$_QUEUE_TABLES_PKEY','DBMS_LOCK_ALLOCATED_PKEY','QUEUE_TBL_UNIQUE','QUEUE_UNIQUE','SYS_JOBS_PKEY');",
            "index_count_by_user": "SELECT ALL_USERS.USERNAME, COUNT(*) INDEX_COUNT FROM SYS_CLASS, ALL_USERS WHERE SYS_CLASS.RELOWNER=ALL_USERS.USER_ID AND RELNAMESPACE != 11 AND RELKIND = 'i' AND RELNAME NOT IN ('AQ$_QUEUES_PKEY','AQ$_QUEUE_TABLES_PKEY','DBMS_LOCK_ALLOCATED_PKEY','QUEUE_TBL_UNIQUE','QUEUE_UNIQUE','SYS_JOBS_PKEY') GROUP BY 1;",
            "view_count_total": "SELECT COUNT(*) TOTAL_VIEW_NUM FROM SYS_CLASS WHERE RELNAMESPACE != 11 AND RELKIND = 'v' AND RELNAME NOT IN ('DBA_JOBS','USER_JOBS');",
            "view_count_by_user": "SELECT ALL_USERS.USERNAME, COUNT(*) VIEW_COUNT FROM SYS_CLASS, ALL_USERS WHERE SYS_CLASS.RELOWNER=ALL_USERS.USER_ID AND RELNAMESPACE != 11 AND RELKIND = 'v' AND RELNAME NOT IN ('DBA_JOBS','USER_JOBS') GROUP BY 1;",
            "proc_count_total": "SELECT COUNT(*) TOTAL_PROC_NUM FROM SYS_PROC WHERE PRONAMESPACE NOT IN (11,12) AND PRONAME NOT IN ('LT_CONCAT','WM_CONCAT');",
            "proc_count_by_user": "SELECT USERNAME, COUNT(*) PROCEDURE_COUNT FROM SYS_PROC, ALL_USERS WHERE SYS_PROC.PROOWNER=ALL_USERS.USER_ID AND PRONAMESPACE NOT IN (11,12) GROUP BY 1;",
        }
    },
    "performance": {
        "label": "性能监控",
        "queries": {
            "session_count": "SELECT COUNT(*) AS CONNECTION_COUNT FROM V_SYS_SESSIONS WHERE APPNAME != 'isql';",
            "session_by_ip": "SELECT COUNT(*), USER_IP FROM V_SYS_SESSIONS WHERE APPNAME != 'isql' GROUP BY USER_IP ORDER BY COUNT(*) DESC;",
            "deadlock_count": "SELECT COUNT(*) FROM V$SESSION WHERE SID IN (SELECT SID FROM V$LOCK WHERE BLOCK=1);",
            "wait_chains": "SELECT * FROM V$WAIT_CHAINS;",
            "active_queries": "SELECT \"SESSION ID\", APPNAME, USER_IP, \"CURRENT USER\", \"CURRENT SQL\", \"LAST SQL\", LOGONTIME FROM V_SYS_SESSIONS WHERE APPNAME != 'isql';",
            "non_auto_commit": "SELECT COUNT(*) AS NON_AUTO_COMMIT_COUNT FROM V$TRANSACTION WHERE EXPLICIT_TRANS='t';",
            "idle_non_auto_commit": "SELECT COUNT(*) AS IDLE_NON_AUTO_COMMIT FROM V$TRANSACTION VT, V$SESSION VS WHERE VT.SESSION_ID=VS.SID AND VT.EXPLICIT_TRANS='t' AND VS.CURRENT_SQL IS NULL;",
            "db_memory": "SELECT * FROM V$GLOBAL_MEMORY;",
            "slow_sql": "SELECT \"TIME(s)\", SQL FROM V_SYS_TOP_COST_SQLS WHERE \"TIME(s)\" > 0.5 AND SQL NOT LIKE 'SELECT%FROM V_SYS_TOP_COST_SQLS%' AND SQL NOT LIKE 'SELECT%FROM V_SYS_SESSIONS%' ORDER BY \"TIME(s)\" DESC LIMIT 20;",
        }
    },
}


class OscarAdapter(DBAdapter):
    db_type = "oscar"
    label = "Oscar (神通)"
    default_port = 2003
    default_user = "SYSDBA"
    default_db = "OSRDB"
    cli_tool = "isql"
    cli_heredoc = True
    cli_win_file = True
    query_sets = QUERY_SETS
