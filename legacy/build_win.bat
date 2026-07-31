@echo off
REM Windows 二进制编译脚本
REM 前提: pip install pyinstaller

set VERSION=1.0.0

echo === 编译 Windows 二进制 ===

pyinstaller --onefile --name oscar-monitor ^
    --add-data "static;static" ^
    --add-data "templates;templates" ^
    --hidden-import flask --hidden-import paramiko --hidden-import apscheduler ^
    app.py

echo 二进制: dist\oscar-monitor.exe

REM 打包 Inno Setup
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" setup.iss
) else (
    echo Inno Setup 未安装，跳过 exe 打包
    echo 请安装后运行: iscc setup.iss
)
