"""pytest 共享夹具：临时数据目录 + 依赖覆盖隔离全局单例。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.config import Settings
from app.main import create_app
from app.services.auth_service import UserService
from app.services.cache import CacheStore
from app.services.config_service import ConfigService
from app.services.export_service import ExportService
from app.services.persist import LogPersistService
from app.services.scheduler import CollectScheduler
from app.services.server_service import ServerService
from app.services.trend import TrendStore


@pytest.fixture()
def settings(tmp_path) -> Settings:
    s = Settings(
        data_dir=tmp_path / "data",
        secret_key="test-secret-key-0123456789abcdef0123456789abcdef",
        log_enabled=False,
        storage_backend="json",
        collect_workers=2,
    )
    s.ensure_dirs()
    return s


@pytest.fixture()
def client(settings):
    """构造使用测试 Settings 的独立服务实例，避免污染全局单例。"""
    from app.repositories import get_server_repo, get_user_repo

    user_service = UserService(get_user_repo(settings), settings)
    server_service = ServerService(get_server_repo(settings), settings)
    cache = CacheStore()
    trend = TrendStore(max_points=settings.trend_max_points)
    log_service = LogPersistService(settings)
    export_service = ExportService(settings, server_service, cache)
    scheduler = CollectScheduler(settings, server_service, cache, trend, log_service)
    config_service = ConfigService(settings)

    app = create_app(settings=settings, start_scheduler=False)
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    app.dependency_overrides[deps.get_user_service_dep] = lambda: user_service
    app.dependency_overrides[deps.get_server_service_dep] = lambda: server_service
    app.dependency_overrides[deps.get_cache_dep] = lambda: cache
    app.dependency_overrides[deps.get_trend_dep] = lambda: trend
    app.dependency_overrides[deps.get_scheduler_dep] = lambda: scheduler
    app.dependency_overrides[deps.get_export_service_dep] = lambda: export_service
    app.dependency_overrides[deps.get_log_service_dep] = lambda: log_service
    app.dependency_overrides[deps.get_config_service_dep] = lambda: config_service
    # 每个测试使用独立的限速器，避免 IP 封禁状态跨测试污染
    from app.core.rate_limit import LoginRateLimiter, get_login_limiter

    limiter = LoginRateLimiter(settings.login_max_failures, settings.login_window_seconds, settings.login_ban_duration)
    app.dependency_overrides[get_login_limiter] = lambda: limiter

    with TestClient(app) as c:
        c.app.state._test_services = {
            "user": user_service,
            "server": server_service,
            "cache": cache,
            "trend": trend,
            "log": log_service,
            "export": export_service,
            "scheduler": scheduler,
            "config": config_service,
        }
        yield c


@pytest.fixture()
def admin_token(client) -> str:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture()
def auth_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}
