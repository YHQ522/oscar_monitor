"""FastAPI 应用工厂与入口。"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, config, control, reports, servers, sql_terminal, stream
from .config import Settings, get_settings
from .services.scheduler import get_collect_scheduler

logger = logging.getLogger("oscar_monitor")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _frontend_dist_dir() -> Path | None:
    """定位前端构建产物 frontend/dist。

    优先在 PyInstaller 冻结（_MEIPASS）目录下查找，其次回退到源码目录，
    兼容「开发 / 源码部署 / 单文件打包」三种运行形态。
    """
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        bundled = meipass / "frontend" / "dist"
        if bundled.exists():
            return bundled
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def create_app(settings: Settings | None = None, start_scheduler: bool = True) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_scheduler:
            get_collect_scheduler(cfg).start()
        logger.info("oscar-monitor 后端启动，数据目录: %s", cfg.data_dir)
        yield
        if start_scheduler:
            get_collect_scheduler(cfg).shutdown()

    app = FastAPI(title="oscar-monitor", version="2.0.0", lifespan=lifespan)

    # CORS：开发时允许 Vite dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5080",
            "http://127.0.0.1:5080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(auth.router)
    app.include_router(servers.router)
    app.include_router(control.router)
    app.include_router(config.router)
    app.include_router(reports.router)
    app.include_router(sql_terminal.router)
    app.include_router(stream.router)

    # 全局异常处理
    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, _exc: Exception):
        logger.exception("未处理异常: %s %s", request.method, request.url.path)
        # 不向客户端泄露内部异常细节（含路径/SQL/内部状态），仅记录日志
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    # 前端静态资源（生产模式：frontend/dist 构建产物）
    frontend_dist = _frontend_dist_dir()
    if frontend_dist is not None and frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            target = frontend_dist / full_path
            if full_path and target.is_file():
                return FileResponse(target)
            index = frontend_dist / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=5080, reload=True)
