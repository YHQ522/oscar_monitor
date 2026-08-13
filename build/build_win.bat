@echo off
setlocal
chcp 65001 >nul
REM ============================================================
REM  oscar-monitor  Windows 免环境打包脚本
REM  产物:
REM    build\dist\oscar-monitor.exe               单文件可执行程序
REM    build\dist\oscar-monitor-setup-2.0.0.exe   安装包（需 Inno Setup 6）
REM  前置: Python 3.11+ 与 Node.js 18+ 已安装并加入 PATH
REM  用法: 双击运行，或在命令行执行 build_win.bat
REM ============================================================
cd /d "%~dp0.."

echo [1/5] 构建前端静态资源...
pushd frontend
call npm install --no-audit --no-fund
if errorlevel 1 goto :err
call npm run build
if errorlevel 1 goto :err
popd

echo [2/5] 检查 Python...
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.11+ 并加入 PATH
    goto :err
)
python -c "import sys; v=sys.version_info; assert (3,11) <= (v.major,v.minor) <= (3,12), 'x'; print('Python %d.%d.%d' % v[:3])"
if errorlevel 1 (
    echo [错误] 需要 Python 3.11 或 3.12（PyInstaller 兼容性最佳），当前版本不受支持
    goto :err
)

echo [3/5] 安装后端依赖（含 PyInstaller）...
pushd backend
python -m pip install --upgrade pip --quiet
python -m pip install -e . --quiet
if errorlevel 1 goto :err
popd
python -m pip install pyinstaller pillow --quiet
if errorlevel 1 goto :err

echo [4/5] 生成应用图标...
python build\make_icon.py
if errorlevel 1 echo （图标生成失败，将使用 PyInstaller 默认图标）

echo [5/5] PyInstaller 单文件打包（首次约需数分钟）...
pushd build
python -m PyInstaller --noconfirm --clean oscar_monitor.spec
if errorlevel 1 goto :err
popd

echo [6/6] 编译 Windows 安装包（Inno Setup）...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC (
    "%ISCC%" /Qp build\setup.iss
    if errorlevel 1 goto :err
) else (
    echo [提示] 未安装 Inno Setup 6（winget install JRSoftware.InnoSetup），跳过安装包编译
)

echo.
echo ============================================================
echo  打包完成!
echo  单文件程序: build\dist\oscar-monitor.exe
echo  安装包:     build\dist\oscar-monitor-setup-2.0.0.exe
echo  使用方法: 安装包可在任意 Windows 机器上安装使用（无需 Python）
echo  访问地址: http://127.0.0.1:5080   默认账号 admin / admin123
echo  数据目录: C:\ProgramData\OscarMonitor\data（安装版）
echo ============================================================
pause
exit /b 0

:err
echo.
echo [错误] 打包失败，请查看上方日志
pause
exit /b 1
