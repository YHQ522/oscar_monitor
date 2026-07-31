"""启停管控路由：数据库服务与应用启停。"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ..services.collector import app_control, db_control
from ..services.server_service import ServerService
from .deps import any_permission, get_current_user, get_server_service_dep, require_permission

router = APIRouter(prefix="/api", tags=["control"])

ACTIONS = ("start", "stop", "restart", "status")


@router.post("/servers/{server_id}/db-control", dependencies=[Depends(any_permission("control_view", "control_exec"))])
async def api_db_control(
    server_id: str,
    data: dict,
    user: dict = Depends(get_current_user),
    server_service: ServerService = Depends(get_server_service_dep),
):
    server = server_service.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    action = data.get("action", "status")
    if action not in ACTIONS:
        raise HTTPException(status_code=400, detail="无效的操作")
    if action != "status" and not (user.get("is_admin") or "control_exec" in user.get("perms", [])):
        raise HTTPException(status_code=403, detail="无执行权限")
    result = await asyncio.to_thread(db_control, server, action)
    return result


@router.post("/servers/{server_id}/app-control", dependencies=[Depends(any_permission("control_view", "control_exec"))])
async def api_app_control(
    server_id: str,
    data: dict,
    user: dict = Depends(get_current_user),
    server_service: ServerService = Depends(get_server_service_dep),
):
    server = server_service.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务不存在")
    action = data.get("action", "status")
    app_name = data.get("app")
    if action not in ACTIONS:
        raise HTTPException(status_code=400, detail="无效的操作")
    if not app_name:
        raise HTTPException(status_code=400, detail="请指定应用名称")
    if action != "status" and not (user.get("is_admin") or "control_exec" in user.get("perms", [])):
        raise HTTPException(status_code=403, detail="无执行权限")
    result = await asyncio.to_thread(app_control, server, app_name, action)
    return result
