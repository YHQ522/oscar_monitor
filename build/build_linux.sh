#!/bin/bash
# ============================================================
#  oscar-monitor  Linux 免环境打包脚本
#  产物:
#    build/dist/oscar-monitor          单文件二进制（免 Python/Node）
#    build/dist/oscar-monitor-setup-<版本>-linux-x86_64.sh  自解压安装包
#  前置: Python 3.11+ 与 Node.js 18+；需 root 才可执行 systemctl 相关安装
#  用法: bash build_linux.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

VERSION="2.0.0"
OUTPUT_DIR="build/dist"
SETUP_NAME="oscar-monitor-setup-${VERSION}-linux-x86_64.sh"

PYTHON="$(command -v python3 || command -v python)"

echo "[1/5] 构建前端静态资源..."
( cd frontend && npm ci --no-audit --no-fund && npm run build )

echo "[2/5] 检查 Python..."
if [ -z "$PYTHON" ]; then echo "[错误] 未找到 python3"; exit 1; fi
"$PYTHON" --version
"$PYTHON" -c "import sys; v=sys.version_info; assert (3,11) <= (v.major,v.minor) <= (3,12), 'x'; print('Python %d.%d.%d' % v[:3])" \
    || { echo "[错误] 需要 Python 3.11 或 3.12（PyInstaller 兼容性最佳）"; exit 1; }

echo "[3/5] 安装后端依赖（含 PyInstaller / pillow）..."
( cd backend && "$PYTHON" -m pip install --upgrade pip --quiet && "$PYTHON" -m pip install -e . --quiet )
"$PYTHON" -m pip install pyinstaller pillow --quiet

echo "[4/5] 生成图标并 PyInstaller 单文件打包（首次约需数分钟）..."
"$PYTHON" build/make_icon.py
( cd build && "$PYTHON" -m PyInstaller --noconfirm --clean oscar_monitor.spec )

echo "[5/5] 生成自解压安装包..."
BIN="$OUTPUT_DIR/oscar-monitor"
if [ ! -f "$BIN" ]; then echo "[错误] 二进制未生成"; exit 1; fi

PKG_DIR="$OUTPUT_DIR/_pkg"
rm -rf "$PKG_DIR" && mkdir -p "$PKG_DIR"
cp "$BIN" "$PKG_DIR/oscar-monitor"
cp build/install_linux.sh "$PKG_DIR/install_linux.sh"
chmod +x "$PKG_DIR/install_linux.sh"

SETUP="$OUTPUT_DIR/$SETUP_NAME"
cat > "$SETUP" << 'HEADER'
#!/bin/bash
# oscar-monitor 自解压安装包（内置单文件二进制）
set -e
TMPDIR=$(mktemp -d /tmp/oscar-install.XXXXXX)
echo "正在解压安装包..."
ARCHIVE_LINE=$(awk '/^__ARCHIVE__$/ {print NR+1; exit 0}' "$0")
tail -n+$ARCHIVE_LINE "$0" | tar -xzf - -C "$TMPDIR"
cd "$TMPDIR"
bash install_linux.sh
rm -rf "$TMPDIR"
exit 0
__ARCHIVE__
HEADER

( cd "$PKG_DIR" && tar -czf - oscar-monitor install_linux.sh ) >> "$SETUP"
chmod +x "$SETUP"
rm -rf "$PKG_DIR"

echo ""
echo "============================================"
echo "  打包完成！"
echo "  单文件二进制: $OUTPUT_DIR/oscar-monitor"
echo "  自解压安装包: $OUTPUT_DIR/$SETUP_NAME"
echo "  服务器安装:   sudo bash $OUTPUT_DIR/$SETUP_NAME"
echo "============================================"
