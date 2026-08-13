#!/bin/bash
# oscar-monitor Linux 安装脚本（由自解压安装包调用，需 root）
set -e

INSTALL_DIR="/opt/oscar_monitor"
SERVICE_NAME="oscar-monitor"
PORT="${OSCAR_PORT:-5080}"

if [ "$(id -u)" -ne 0 ]; then
    echo "请使用 root 权限安装：sudo bash $0"
    exit 1
fi

# 交互式询问端口（仅当有 TTY 且未显式指定 OSCAR_PORT 时）
if [ -z "${OSCAR_PORT}" ] && [ -t 0 ]; then
    read -r -p "请输入服务监听端口（默认 5080）: " ANSWER
    if [ -n "$ANSWER" ]; then
        PORT="$ANSWER"
    fi
fi

# 校验端口
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "[错误] 无效端口: $PORT（应在 1-65535 之间）"
    exit 1
fi

echo ">>> 安装目录: ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"
install -m 0755 "$(dirname "$0")/oscar-monitor" "$INSTALL_DIR/oscar-monitor"
mkdir -p "$INSTALL_DIR/data"

# 首次安装写入初始端口配置（升级安装保留已有 config.json）
CFG="$INSTALL_DIR/data/config.json"
if [ ! -f "$CFG" ]; then
    echo "{\"port\": $PORT}" > "$CFG"
    echo ">>> 监听端口: ${PORT}"
else
    echo ">>> 已存在 config.json，保留现有端口配置"
fi

# 注册 systemd 服务（开机自启 + 崩溃自动重启；端口由 config.json 决定）
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=oscar-monitor 数据库监控管控平台
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/oscar-monitor --host 0.0.0.0
Restart=on-failure
RestartSec=3
Environment=OSCAR_DATA_DIR=${INSTALL_DIR}/data

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "============================================"
echo "  安装完成！"
echo "  程序:     ${INSTALL_DIR}/oscar-monitor"
echo "  数据目录: ${INSTALL_DIR}/data"
echo "  访问地址: http://<本机IP>:${PORT}"
echo "  默认账号: admin / admin123（首次登录请修改）"
echo "  修改端口: 编辑 ${INSTALL_DIR}/data/config.json 的 port 字段后 systemctl restart ${SERVICE_NAME}"
echo "  服务管理: systemctl status ${SERVICE_NAME}"
echo "============================================"
