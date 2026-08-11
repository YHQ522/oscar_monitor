#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="1.0.0"
OUTPUT="dist/OscarMonitor_Setup.sh"

echo "=== 编译 Linux 二进制 ==="

# 1. 编译
python3 -m PyInstaller --onefile --name oscar-monitor \
    --add-data "static:static" \
    --add-data "templates:templates" \
    --hidden-import flask --hidden-import paramiko --hidden-import apscheduler \
    app.py

echo "二进制: dist/oscar-monitor ($(du -h dist/oscar-monitor | cut -f1))"
echo ""

# 2. 自解压打包（替代 makeself）
echo "=== 生成安装包 ==="

mkdir -p build_pkg dist
cp dist/oscar-monitor build_pkg/
cp install.sh build_pkg/

cat > "$OUTPUT" << 'HEADER'
#!/bin/bash
set -e
TMPDIR=$(mktemp -d /tmp/oscar-install.XXXXXX)
echo ""
echo "========================================"
echo "  管控平台 安装程序"
echo "========================================"
echo ""
echo "正在解压..."
ARCHIVE_LINE=$(awk '/^__ARCHIVE__$/ {print NR+1; exit 0}' "$0")
tail -n+$ARCHIVE_LINE "$0" | tar -xz -C "$TMPDIR"
echo "解压完成，开始安装..."
cp "$TMPDIR/oscar-monitor" "$TMPDIR/install.sh" .
bash "$TMPDIR/install.sh"
rm -rf "$TMPDIR"
exit 0
__ARCHIVE__
HEADER

cd build_pkg
tar -czf - oscar-monitor install.sh >> "../$OUTPUT"
cd ..

chmod +x "$OUTPUT"
rm -rf build_pkg

echo "完成: $OUTPUT ($(du -h $OUTPUT | cut -f1))"
echo "安装: sudo bash $OUTPUT"
