#!/bin/bash
set -e

APP_NAME="oscar-monitor"
VERSION="1.0.0"
OUTPUT="dist/OscarMonitor_Setup.sh"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="/tmp/${APP_NAME}-build"

echo "=== 管控平台 打包工具 ==="
echo "版本: ${VERSION}"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" dist

# 复制源文件
cp "$SCRIPT_DIR/app.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/collector.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/auth.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/persist.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/db_config.py" "$BUILD_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$BUILD_DIR/"
cp -r "$SCRIPT_DIR/static" "$BUILD_DIR/" 2>/dev/null
cp -r "$SCRIPT_DIR/templates" "$BUILD_DIR/" 2>/dev/null

# 复制安装脚本
cp "$SCRIPT_DIR/install.sh" "$BUILD_DIR/"

# 下载离线依赖
echo "[1/2] 下载依赖..."
mkdir -p "$BUILD_DIR/deps"
pip3 download -d "$BUILD_DIR/deps" flask paramiko apscheduler 2>/dev/null || \
    pip download -d "$BUILD_DIR/deps" flask paramiko apscheduler 2>/dev/null || \
    echo "警告: 下载失败，安装时将联网获取"

# 打包
echo "[2/2] 生成 ${OUTPUT}..."
makeself --notemp --needroot "$BUILD_DIR" "$OUTPUT" "管控平台 v${VERSION}" ./install.sh

rm -rf "$BUILD_DIR"
echo "完成: ${OUTPUT} ($(du -h ${OUTPUT} | cut -f1))"
echo "安装: sudo ./${OUTPUT}"
