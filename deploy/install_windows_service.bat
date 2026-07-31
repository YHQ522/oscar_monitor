@echo off
REM ============================================================
REM  oscar-monitor 后端注册为 Windows 服务（使用 NSSM）
REM  前置要求：
REM    1. 已执行 cd backend && uv sync 完成依赖安装
REM    2. 已安装 NSSM 并将 nssm.exe 加入 PATH（https://nssm.cc/download）
REM  用法：双击运行 install_windows_service.bat
REM ============================================================
chcp 65001 >nul
setlocal

set SVC_NAME=oscar-monitor
set APP_DIR=%~dp0..
set PYTHON=%APP_DIR%\backend\.venv\Scripts\python.exe
set LOG_DIR=%APP_DIR%\logs

if not exist "%PYTHON%" (
  echo [错误] 未找到虚拟环境 Python: %PYTHON%
  echo 请先执行: cd backend ^&^& uv sync
  pause
  exit /b 1
)

where nssm >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 nssm.exe，请先安装并加入 PATH
  echo 下载地址: https://nssm.cc/download
  pause
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo 正在安装服务 %SVC_NAME% ...
nssm install %SVC_NAME% "%PYTHON%" "run.py --host 0.0.0.0 --port 5080"
nssm set %SVC_NAME% AppDirectory "%APP_DIR%\backend"
nssm set %SVC_NAME% AppStdout "%LOG_DIR%\out.log"
nssm set %SVC_NAME% AppStderr "%LOG_DIR%\err.log"
nssm set %SVC_NAME% AppRotateFiles 1
nssm set %SVC_NAME% AppRotateBytes 10485760
nssm set %SVC_NAME% Start SERVICE_AUTO_START
nssm start %SVC_NAME%

echo.
echo 服务已安装并启动。管理命令：
echo   查看状态:  nssm status %SVC_NAME%
echo   停止服务:  nssm stop %SVC_NAME%
echo   卸载服务:  nssm remove %SVC_NAME% confirm
echo.
echo 生产环境请设置环境变量 OSCAR_SECRET_KEY（>=32 字节随机串）后再启动。
pause
