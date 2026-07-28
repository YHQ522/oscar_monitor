#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${1:-5080}"

echo "========================================"
echo "  管控平台 - 开发启动"
echo "========================================"

if ! command -v python3 &>/dev/null; then
    echo "[ERROR] 未找到 python3"
    exit 1
fi
echo "Python: $(python3 --version)"

if ! python3 -c "import flask" 2>/dev/null; then
    echo "[INFO] 安装依赖..."
    pip3 install flask paramiko apscheduler
fi

mkdir -p data
echo "访问: http://localhost:${PORT}"

python3 app.py --port "${PORT}"
