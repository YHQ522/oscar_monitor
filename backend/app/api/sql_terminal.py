"""Web SQL 终端路由：只读查询校验与执行（支持页面关闭即时取消）。"""
from __future__ import annotations

import asyncio
import re
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..core.db_exec import (
    build_sql_cmd,
    output_has_error,
    parse_isql_output,
    run_local_interruptible,
    ssh_exec_sql_interruptible,
    temp_sql_path,
)
from ..core.ssh import need_ssh, ssh_connect
from ..services.server_service import ServerService
from .deps import any_permission, get_server_service_dep

router = APIRouter(prefix="/api", tags=["sql"])

SAFE_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW", "DESC", "DESCRIBE")
DANGEROUS = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "TRUNCATE",
             "GRANT", "REVOKE", "EXEC", "EXECUTE", "CALL", "MERGE", "REPLACE")
# 以 SELECT 开头但可读写服务器文件的高危子句（绕过只读限制）
FILE_IO = ("INTO OUTFILE", "INTO DUMPFILE", "LOAD_FILE")

# FROM 段/WHERE 段之后的顶层关键字（用于截取扫描区间）
_SEGMENT_KEYS = ("WHERE", "GROUP", "ORDER", "LIMIT", "HAVING", "UNION", "OFFSET", "FETCH", "QUALIFY")


def detect_cartesian_risk(sql: str) -> str | None:
    """静态检测笛卡尔积风险：顶层 FROM 多表逗号连接且缺少等值连接条件。

    规则：FROM 段（顶层）含 ≥2 张表（逗号分隔）时，要求存在顶层 WHERE，
    且 WHERE 中的等值条件（=）数量 ≥ 表数-1，否则视为潜在笛卡尔积，返回风险描述。
    显式 JOIN 写法、括号内（子查询/函数）的逗号不参与判断。
    """
    s = re.sub(r"--[^\n]*", "", sql)
    depth = 0
    n = len(s)
    top = [False] * n
    for i, ch in enumerate(s):
        top[i] = depth == 0
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)

    def top_word_positions(word: str) -> list[int]:
        return [m.start() for m in re.finditer(r"\b" + word + r"\b", s, re.IGNORECASE) if top[m.start()]]

    from_pos = top_word_positions("FROM")
    if not from_pos:
        return None
    f_start = from_pos[0]
    f_end = f_start + 4

    boundaries = [
        p for kw in _SEGMENT_KEYS for p in top_word_positions(kw) if p > f_end
    ]
    seg_end = min(boundaries) if boundaries else n
    from_seg = s[f_end:seg_end]

    tables = sum(1 for i, ch in enumerate(from_seg) if ch == "," and top[f_end + i]) + 1
    if tables < 2:
        return None

    where_pos = [p for p in top_word_positions("WHERE") if p > f_end and p <= seg_end]
    if not where_pos:
        # 高危：多表逗号连接且无 WHERE —— 直接阻止执行
        return f"BLOCK:{tables} 张表使用逗号连接且没有 WHERE 条件，属于高危笛卡尔积，已阻止执行"

    w_end = where_pos[0] + 5
    boundaries2 = [
        p for kw in _SEGMENT_KEYS for p in top_word_positions(kw) if p > w_end
    ]
    wseg_end = min(boundaries2) if boundaries2 else n
    wseg = s[w_end:wseg_end]

    eq = 0
    i = 0
    while i < len(wseg):
        if not top[w_end + i]:
            i += 1
            continue
        if wseg[i] == "=":
            prev = wseg[i - 1] if i > 0 else ""
            nxt = wseg[i + 1] if i + 1 < len(wseg) else ""
            if prev not in ("<", ">", "!") and nxt != "=":
                eq += 1
        i += 1
    if eq < tables - 1:
        return (
            f"检测到 {tables} 张表逗号连接，WHERE 中等值连接条件仅 {eq} 个"
            f"（至少需要 {tables - 1} 个），存在笛卡尔积风险"
        )
    return None


@router.post("/servers/{server_id}/sql-query", dependencies=[Depends(any_permission("admin", "sql_terminal"))])
async def sql_query(request: Request, server_id: str, data: dict, server_service: ServerService = Depends(get_server_service_dep)):
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

    # 笛卡尔积风险预检：高危（无 WHERE 多表）直接阻止；中危（条件不足）需确认后执行
    risk = detect_cartesian_risk(sql)
    if risk:
        if risk.startswith("BLOCK:"):
            raise HTTPException(
                status_code=403,
                detail="[CARTESIAN_BLOCKED] " + risk[6:]
                + "。该语句不会在监控平台执行；如确有需要，请直接登录数据库谨慎执行。",
            )
        if not data.get("risk_confirmed"):
            return JSONResponse(status_code=428, content={"detail": "[CARTESIAN_RISK] " + risk})

    # 执行放在后台线程；主协程监听客户端断开，断开后立即置位取消并强制关闭连接
    cancel_event = threading.Event()
    holder: dict[str, Any] = {}

    def worker() -> None:
        try:
            if need_ssh(server):
                client = ssh_connect(server, timeout=15)
                holder["client"] = client
                try:
                    out, err, ec = ssh_exec_sql_interruptible(client, server, sql, cancel_event, timeout=60)
                finally:
                    client.close()
            else:
                sql_file = temp_sql_path(server)
                _, cmd = build_sql_cmd(server, sql, sql_file)
                out, err, ec = run_local_interruptible(cmd, cancel_event, timeout=60)
            holder["result"] = (out, err, ec)
        except Exception as e:  # noqa: BLE001
            holder["error"] = e

    task = asyncio.create_task(asyncio.to_thread(worker))
    try:
        while not task.done():
            if await request.is_disconnected():
                # 页面已关闭：置位取消，worker 会在远端 pkill + 关闭通道后自行结束；
                # 超时兑底再强制关闭 SSH（断开远端连接，sshd 会发 SIGHUP）
                cancel_event.set()
                try:
                    await asyncio.wait_for(task, timeout=15)
                except asyncio.TimeoutError:
                    client = holder.get("client")
                    if client is not None:
                        try:
                            client.close()
                        except Exception:  # noqa: BLE001
                            pass
                    await task
                return {"cancelled": True}
            await asyncio.sleep(0.2)
    finally:
        if not task.done():
            cancel_event.set()

    if holder.get("error"):
        err = holder["error"]
        if isinstance(err, TimeoutError):
            raise HTTPException(status_code=500, detail=str(err))
        raise HTTPException(status_code=500, detail=str(err))
    out, err, ec = holder["result"]
    # 退出码非 0 或输出含错误特征均视为失败
    # （部分 CLI 语法错误时退出码仍为 0，错误只写在 stdout）
    if ec != 0 or output_has_error(out):
        raise HTTPException(status_code=422, detail=(err or out or "执行失败").strip()[:500])
    return parse_isql_output(out, "sql_query")
