"""FastAPI 依赖注入：服务实例获取 + JWT 认证 + 权限校验。"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings, get_settings
from ..core.security import decode_token
from ..services.auth_service import UserService, get_user_service
from ..services.cache import CacheStore, get_cache
from ..services.config_service import ConfigService, get_config_service
from ..services.export_service import ExportService, get_export_service
from ..services.persist import LogPersistService, get_log_service
from ..services.scheduler import CollectScheduler, get_collect_scheduler
from ..services.server_service import ServerService, get_server_service
from ..services.trend import TrendStore, get_trend_store

_bearer = HTTPBearer(auto_error=False)


# ── 服务依赖 ──
def get_settings_dep() -> Settings:
    return get_settings()


def get_user_service_dep(settings: Settings = Depends(get_settings_dep)) -> UserService:
    return get_user_service(settings)


def get_server_service_dep(settings: Settings = Depends(get_settings_dep)) -> ServerService:
    return get_server_service(settings)


def get_cache_dep() -> CacheStore:
    return get_cache()


def get_trend_dep(settings: Settings = Depends(get_settings_dep)) -> TrendStore:
    return get_trend_store(settings.trend_max_points)


def get_scheduler_dep(settings: Settings = Depends(get_settings_dep)) -> CollectScheduler:
    return get_collect_scheduler(settings)


def get_export_service_dep(settings: Settings = Depends(get_settings_dep)) -> ExportService:
    return get_export_service(settings)


def get_log_service_dep(settings: Settings = Depends(get_settings_dep)) -> LogPersistService:
    return get_log_service(settings)


def get_config_service_dep(settings: Settings = Depends(get_settings_dep)) -> ConfigService:
    return get_config_service(settings)


# ── 认证 ──
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings_dep),
    user_service: UserService = Depends(get_user_service_dep),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或会话已过期")
    payload = decode_token(credentials.credentials, settings.secret_key)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或会话已过期")
    user = user_service.get_user(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


def require_permission(perm: str) -> Callable:
    """返回一个校验指定权限的依赖。"""

    def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("is_admin") or perm in user.get("perms", []):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")

    return checker


def any_permission(*perms: str) -> Callable:
    """拥有任一权限即可访问。"""

    def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("is_admin") or any(p in user.get("perms", []) for p in perms):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限")

    return checker


def get_client_ip(request: Request) -> str:
    """获取客户端 IP；支持反向代理的 X-Forwarded-For（取第一个非私有 IP）。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        for ip in parts:
            if not ip.startswith(("10.", "172.", "192.168.", "127.", "169.254.")):
                return ip
        if parts:
            return parts[0]
    return request.client.host if request.client else "127.0.0.1"
