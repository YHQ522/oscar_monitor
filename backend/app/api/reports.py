"""报表路由：Excel/CSV 导出、导出历史。"""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from ..config import Settings
from ..services.export_service import ExportService
from .deps import any_permission, get_export_service_dep, get_settings_dep, require_permission

router = APIRouter(prefix="/api", tags=["reports"])


@router.get("/export/history", dependencies=[Depends(any_permission("admin", "reports_view"))])
def export_history(export_service: ExportService = Depends(get_export_service_dep)):
    return export_service.history()


@router.delete("/export/history/{filename}", dependencies=[Depends(require_permission("admin"))])
def delete_history(filename: str, export_service: ExportService = Depends(get_export_service_dep)):
    export_service.delete_history(filename)
    return {"status": "ok"}


@router.get("/export/download/{filename}", dependencies=[Depends(any_permission("admin", "reports_view"))])
def download_history(filename: str, settings: Settings = Depends(get_settings_dep)):
    """下载历史导出文件（防路径穿越）。"""
    import os

    base = settings.reports_dir.resolve()
    target = (base / os.path.basename(filename)).resolve()
    if not target.is_file() or base not in target.parents:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target, filename=target.name)


@router.post("/export/xlsx", dependencies=[Depends(any_permission("admin", "reports_view"))])
def export_xlsx(
    data: dict,
    export_service: ExportService = Depends(get_export_service_dep),
    settings: Settings = Depends(get_settings_dep),
):
    server_ids = data.get("servers", [])
    categories = data.get("categories", [])
    os_checks = data.get("os_checks", [])
    organize_by = data.get("organize_by", "server")
    try:
        filename = export_service.export_xlsx(server_ids, categories, os_checks, organize_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filepath = settings.reports_dir / filename
    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
        headers={"X-Filename": quote(filename, safe="")},
    )


@router.get("/export/csv/{server_id}", dependencies=[Depends(any_permission("dashboard", "servers_view"))])
def export_csv(server_id: str, export_service: ExportService = Depends(get_export_service_dep)):
    try:
        filename, content = export_service.export_csv(server_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # 防响应头注入：文件名仅保留安全字符
    safe_name = re.sub(r"[^0-9a-zA-Z._-]", "_", filename)
    return PlainTextResponse(
        content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={safe_name}"},
    )
