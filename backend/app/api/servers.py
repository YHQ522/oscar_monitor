"""服务器路由：CRUD、采集、缓存数据、健康评分、趋势、连接测试、日志。"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..config import Settings
from ..models.server import ServerCreate, ServerOut, ServerUpdate
from ..services.cache import CacheStore
from ..services.collector import test_connection
from ..services.health import calc_health_score, smooth_score
from ..services.persist import LogPersistService
from ..services.scheduler import CollectScheduler
from ..services.server_service import ServerService
from ..services.trend import TrendStore
from .deps import (
    any_permission,
    get_cache_dep,
    get_log_service_dep,
    get_scheduler_dep,
    get_server_service_dep,
    get_settings_dep,
    get_trend_dep,
    require_permission,
)

router = APIRouter(prefix="/api", tags=["servers"])


def _safe(server: dict[str, Any]) -> dict[str, Any]:
    return ServerOut.from_server(server).model_dump()


# ═══════════════ CRUD ═══════════════
@router.get("/servers", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def list_servers(server_service: ServerService = Depends(get_server_service_dep)):
    return [_safe(s) for s in server_service.list()]


@router.post("/servers", dependencies=[Depends(require_permission("servers_edit"))])
def add_server(data: ServerCreate, server_service: ServerService = Depends(get_server_service_dep)):
    try:
        server = server_service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "id": server["id"]}


@router.put("/servers/{server_id}", dependencies=[Depends(require_permission("servers_edit"))])
def update_server(
    server_id: str,
    data: ServerUpdate,
    server_service: ServerService = Depends(get_server_service_dep),
    cache: CacheStore = Depends(get_cache_dep),
):
    try:
        server = server_service.update(server_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    cache.drop(server_id)
    return {"status": "ok"}


@router.delete("/servers/{server_id}", dependencies=[Depends(require_permission("servers_edit"))])
def delete_server(
    server_id: str,
    server_service: ServerService = Depends(get_server_service_dep),
    cache: CacheStore = Depends(get_cache_dep),
    trend: TrendStore = Depends(get_trend_dep),
):
    if not server_service.delete(server_id):
        raise HTTPException(status_code=404, detail="服务不存在")
    cache.drop(server_id)
    trend.clear(server_id)
    return {"status": "ok"}


# ═══════════════ 元数据 ═══════════════
@router.get("/meta", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def meta():
    """返回前端渲染所需的元数据：数据库类型、查询集、标签、系统开关。"""
    from ..adapters import all_adapters, get_query_sets
    from ..core.constants import OS_CHECK_LABELS, QUERY_LABELS
    from ..services.config_service import get_config_service

    return {
        "db_types": all_adapters(),
        "query_sets": {t: get_query_sets(t) for t in all_adapters()},
        "query_labels": QUERY_LABELS,
        "os_check_labels": OS_CHECK_LABELS,
        "os_checks": ["memory", "disk", "cpu", "install_path", "os_errors", "db_log_errors"],
        # 系统级日志持久化开关（服务器级 persist_enabled 依赖它）
        "log_enabled": bool(get_config_service().get().get("log_enabled", False)),
    }


# ═══════════════ 采集 ═══════════════
@router.post("/servers/{server_id}/collect", dependencies=[Depends(require_permission("servers_edit"))])
async def collect(
    server_id: str,
    server_service: ServerService = Depends(get_server_service_dep),
    scheduler: CollectScheduler = Depends(get_scheduler_dep),
    cache: CacheStore = Depends(get_cache_dep),
):
    server = server_service.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    result = await asyncio.to_thread(scheduler.collect_one, server)
    return result


@router.post("/servers/{server_id}/collect-partial", dependencies=[Depends(require_permission("servers_edit"))])
async def collect_partial(
    server_id: str,
    data: dict,
    server_service: ServerService = Depends(get_server_service_dep),
    scheduler: CollectScheduler = Depends(get_scheduler_dep),
):
    server = server_service.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    categories = data.get("categories", [])
    os_checks = data.get("os_checks", [])
    if not categories and not os_checks:
        raise HTTPException(status_code=400, detail="请指定采集类别")
    result = await asyncio.to_thread(scheduler.collect_partial, server, categories, os_checks)
    return result


@router.get("/servers/{server_id}/data", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def get_cached(server_id: str, cache: CacheStore = Depends(get_cache_dep)):
    return cache.get(server_id)


@router.get("/servers/{server_id}/health", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def health_score(
    server_id: str,
    cache: CacheStore = Depends(get_cache_dep),
    server_service: ServerService = Depends(get_server_service_dep),
):
    cached = cache.get(server_id)
    if not cached:
        return {"score": None, "msg": "暂无数据，请先采集"}
    server = server_service.get(server_id) or {}
    score, details = calc_health_score(
        cached,
        server.get("enabled_categories"),
        server.get("enabled_os_checks"),
        bool(server.get("skip_db")),
    )
    # 返回平滑后评分（最近 N 次均值，防单次抖动误报）
    return {"score": smooth_score(server_id, score), "details": details}


@router.get("/trends/{server_id}", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def trends(server_id: str, hours: int = 24, trend: TrendStore = Depends(get_trend_dep)):
    return trend.get(server_id, hours=hours)


@router.post("/test-connection", dependencies=[Depends(require_permission("servers_edit"))])
def api_test_connection(data: dict):
    try:
        return test_connection(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════ 日志查询 ═══════════════
@router.get("/health", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def health_all(
    server_service: ServerService = Depends(get_server_service_dep),
    cache: CacheStore = Depends(get_cache_dep),
):
    """批量健康评分：一次返回全部服务器的 score/details（避免前端 N+1 请求）。"""
    result: dict[str, Any] = {}
    for s in server_service.list():
        cached = cache.get(s["id"])
        if not cached:
            result[s["id"]] = {"score": None, "details": {}}
            continue
        score, details = calc_health_score(
            cached,
            s.get("enabled_categories"),
            s.get("enabled_os_checks"),
            bool(s.get("skip_db")),
        )
        result[s["id"]] = {"score": smooth_score(s["id"], score), "details": details}
    return result


@router.get("/servers/{server_id}/log-errors", dependencies=[Depends(require_permission("servers_view"))])
def log_errors(
    server_id: str,
    page: int = 1,
    size: int = 50,
    kw: str = "",
    log_type: str = "",
    server_service: ServerService = Depends(get_server_service_dep),
    log_service: LogPersistService = Depends(get_log_service_dep),
):
    server = server_service.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    server_name = server.get("name") or server.get("ssh_host", "")
    all_logs = log_service.query_logs(server_name, limit=5000)
    if kw:
        kw_lower = kw.lower()
        all_logs = [
            l for l in all_logs
            if kw_lower in (str(l.get("msg", "")) + str(l.get("exec_sql", "")) + str(l.get("exec_user", ""))).lower()
        ]
    if log_type:
        all_logs = [l for l in all_logs if l.get("check_type") == log_type]
    total = len(all_logs)
    start = (page - 1) * size
    return {"logs": all_logs[start:start + size], "total": total, "server": server_name}
