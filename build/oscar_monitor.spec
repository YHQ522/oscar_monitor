# -*- mode: python ; coding: utf-8 -*-
"""oscar-monitor PyInstaller 单文件打包配置（Windows / Linux 通用）。

用法（在本目录执行）：
    python -m PyInstaller --noconfirm --clean oscar_monitor.spec

产物（build/dist/ 下）：
    Windows:  oscar-monitor.exe
    Linux:    oscar-monitor

打包内容：
    - 后端 app 包（FastAPI + uvicorn + paramiko + sqlalchemy 等全部第三方依赖）
    - 前端构建产物 frontend/dist（已 `npm run build`）
"""

import sys
from pathlib import Path

# SPECPATH 是 spec 所在目录（build/），项目根目录在其上一级
PROJECT_ROOT = Path(SPECPATH).parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
ICON_FILE = Path(SPECPATH) / "assets" / "oscar-monitor.ico"

if not FRONTEND_DIST.exists():
    sys.exit(f"[ERROR] 未找到前端构建产物: {FRONTEND_DIST}\n请先执行: cd frontend && npm run build")

block_cipher = None

a = Analysis(
    [str(BACKEND_DIR / "run.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=[
        # 前端构建产物 -> 冻结目录 frontend/dist（main.py 从 _MEIPASS 查找）
        (str(FRONTEND_DIST), "frontend/dist"),
    ],
    hiddenimports=[
        # ---- uvicorn[standard] 动态加载点 ----
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan.on",
        "httptools",
        "websockets",
        "yaml",
        # ---- pydantic-settings 的 .env 支持（模块名 dotenv）----
        "dotenv",
        "pydantic_settings",
        # ---- SQLAlchemy 方言（json 默认 / sqlite 可选）----
        "sqlalchemy.dialects.sqlite",
        # ---- APScheduler 后台调度 ----
        "apscheduler.schedulers.background",
        "apscheduler.triggers.interval",
        "apscheduler.triggers.cron",
        # ---- paramiko / 加密 ----
        "paramiko",
        "cryptography.hazmat.backends.openssl",
        # ---- Excel 导出 / 认证 / 表单 ----
        "openpyxl",
        "jwt",
        "multipart",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "pytest",
        "matplotlib",
        "numpy",
        "scipy",
        "PIL",
        "IPython",
        "jedi",
        "black",
        "pydoc",
        "test",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="oscar-monitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 不依赖 UPX，避免杀软误报与压缩环境差异
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 控制台程序：日志可见，便于排障
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
)
