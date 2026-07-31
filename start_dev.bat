@echo off
REM 一键开发启动：后端(5080) + 前端(5173)
chcp 65001 >nul
echo ==========================================
echo   oscar-monitor v2 开发环境
echo ==========================================
echo 后端: http://127.0.0.1:5080/docs
echo 前端: http://localhost:5173

start "oscar-backend" cmd /k "cd /d %~dp0backend && python run.py --port 5080"
start "oscar-frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
echo 已启动，请稍候...
