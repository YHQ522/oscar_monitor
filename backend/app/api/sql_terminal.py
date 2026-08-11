"""Web SQL 终端路由：只读查询校验与执行。"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException

from ..core.db_exec import build_sql_cmd, parse_isql_output, temp_sql_path
from ..core.ssh import need_ssh, run_local, ssh_connect, ssh_exec
from ..services.server_service import ServerService
from .deps import get_server_service_dep, require_permission

router = APIRouter(prefix="/api", tags=["sql"])

SAFE_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "DESC", "DESCRIBE")
DANGEROUS = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE",
             "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL", "MERGE", "REPLACE")
# 以 SELECT 开头但可读写服务器文件的高危子句（绕过只读限制）
FILE_IO = ("INTO OUTFILE", "INTO DUMPFILE", "LOAD_FILE")


@router.post("/servers/{server_id}/sql-query", dependencies=[Depends(require_permission("admin"))])
def sql_query(server_id: str, data: dict, server_service: ServerService = Depends(get_server_service_dep)):
    server = server_service.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    sql = (data.get("sql", "") or "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="请输入 SQL 语句")

    sql_upper = sql.upper().strip()
    if not any(sql_upper.startswith(p) for p in SAFE_PREFIXES):
        raise HTTPException(status_code=403, detail="仅支持只读查询 (SELECT / WITH / EXPLAIN / SHOW / DESC)")
    for kw in DANGEROUS:
        if re.search(r"\b" + kw + r"\b", sql_upper):
            raise HTTPException(status_code=403, detail=f"禁止使用 {kw} 语句")
    for pat in FILE_IO:
        if pat in sql_upper:
            raise HTTPException(status_code=403, detail=f"禁止使用 {pat}（防止读写服务器文件）")
    if len(sql) > 5000:
        raise HTTPException(status_code=400, detail="SQL 语句过长（最大 5000 字符）")

    sql_file = temp_sql_path(server)
    _, cmd = build_sql_cmd(server, sql, sql_file)
    try:
        if need_ssh(server):
            client = ssh_connect(server, timeout=15)
            try:
                out, err, ec = ssh_exec(client, cmd, timeout=60)
            finally:
                client.close()
        else:
            out, err, ec = run_local(cmd, timeout=60)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))

    if ec != 0 and not out.strip():
        raise HTTPException(status_code=422, detail=err or "执行失败（请检查 CLI 命令与连接配置）")
    return parse_isql_output(out, "sql_query")
