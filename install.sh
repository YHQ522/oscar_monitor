#!/bin/bash
set -e

APP_NAME="oscar-monitor"
INSTALL_DIR="/opt/${APP_NAME}"
PORT="5080"
VERSION="1.0.0"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[X]${NC} $1"; exit 1; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

check_root() { [[ $EUID -ne 0 ]] && err "请使用 root 或 sudo 运行"; }

SRC="$(cd "$(dirname "$0")" && pwd)"

# 检测二进制或源码模式
if [[ -f "$SRC/oscar-monitor" ]]; then
    BIN_MODE=1
    EXEC="$INSTALL_DIR/oscar-monitor"
else
    BIN_MODE=0
    EXEC="python3 ${INSTALL_DIR}/app.py"
fi
GUI=0
command -v zenity &>/dev/null && GUI=1

# ── GUI 安装 ──────────────────────────────
gui_install() {
    zenity --question --title="管控平台安装" --text="欢迎安装管控平台 v${VERSION}\n\n是否开始安装？" --width=400 || err "已取消"

    INSTALL_DIR=$(zenity --entry --title="安装目录" --text="请输入安装目录:" --entry-text="${INSTALL_DIR}" --width=450)
    [[ -z "$INSTALL_DIR" ]] && err "已取消"
    PORT=$(zenity --entry --title="监听端口" --text="请输入监听端口:" --entry-text="${PORT}" --width=450)
    [[ -z "$PORT" ]] && err "已取消"

    if [[ -d "${INSTALL_DIR}/data/config.json" ]]; then
        zenity --warning --title="数据库警告" --text="检测到已配置数据库连接。\n\n如果表结构与程序不一致，可能导致数据丢失。\n建议先备份 ${INSTALL_DIR}/data 目录。" --width=450
    fi

    (
        echo "10"; echo "# 检查环境..."
        if [[ $BIN_MODE -eq 0 ]]; then
            command -v python3 &>/dev/null || { yum install -y python3 python3-pip 2>/dev/null || apt-get install -y python3 python3-pip 2>/dev/null; }
        fi

        echo "25"; echo "# 安装依赖..."
        if [[ $BIN_MODE -eq 1 ]]; then
            echo "(二进制模式，无需依赖)"
        elif [[ -d "$SRC/deps" ]] && ls "$SRC/deps"/*.whl 2>/dev/null|head -1 >/dev/null; then
            pip3 install --no-index --find-links="$SRC/deps" flask paramiko apscheduler 2>&1 | tail -1
        else
            pip3 install flask paramiko apscheduler 2>&1 | tail -1
        fi

        echo "45"; echo "# 复制文件..."
        [[ -d "${INSTALL_DIR}" ]] && systemctl stop ${APP_NAME} 2>/dev/null
        mkdir -p "${INSTALL_DIR}/data"
        if [[ $BIN_MODE -eq 1 ]]; then
            cp "$SRC/oscar-monitor" "${INSTALL_DIR}/"
            chmod +x "${INSTALL_DIR}/oscar-monitor"
        else
            for f in app.py collector.py auth.py persist.py db_config.py requirements.txt; do
                [[ -f "$SRC/$f" ]] && cp "$SRC/$f" "${INSTALL_DIR}/"
            done
            [[ -d "$SRC/static" ]] && cp -r "$SRC/static" "${INSTALL_DIR}/" 2>/dev/null
            [[ -d "$SRC/templates" ]] && cp -r "$SRC/templates" "${INSTALL_DIR}/" 2>/dev/null
        fi

        echo "60"; echo "# 重置数据..."
        rm -f "${INSTALL_DIR}/data/servers.json" "${INSTALL_DIR}/data/users.json" "${INSTALL_DIR}/data/config.json"

        echo "75"; echo "# 注册服务..."
        cat > /etc/systemd/system/${APP_NAME}.service << EOF
[Unit]
Description=管控平台 v${VERSION}
After=network.target
[Service]
Type=simple;User=root;WorkingDirectory=${INSTALL_DIR}
ExecStart=${EXEC} --port ${PORT}
Restart=always;RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload; systemctl enable ${APP_NAME}; systemctl start ${APP_NAME}

        echo "90"; echo "# 防火墙..."
        command -v firewall-cmd &>/dev/null && { firewall-cmd --add-port=${PORT}/tcp --permanent 2>/dev/null; firewall-cmd --reload 2>/dev/null; }

        echo "100"; echo "# 完成"
        sleep 1
    ) | zenity --progress --title="安装中" --text="正在安装..." --percentage=0 --width=400 --auto-close 2>/dev/null || true

    if systemctl is-active --quiet ${APP_NAME}; then
        zenity --info --title="安装完成" --text="安装成功！\n\n访问: http://$(hostname -I | awk '{print $1}'):${PORT}\n管理: systemctl {start|stop|restart|status} ${APP_NAME}\n卸载: sudo ${INSTALL_DIR}/uninstall.sh" --width=450
    else
        zenity --error --title="安装失败" --text="服务未能启动，请检查日志:\njournalctl -u ${APP_NAME} -n 20" --width=450
    fi
}

# ── GUI 卸载 ──────────────────────────────
gui_uninstall() {
    zenity --question --title="卸载管控平台" --text="确认卸载管控平台？\n\n数据将备份到 /tmp/" --width=400 || err "已取消"

    systemctl stop ${APP_NAME} 2>/dev/null || true
    systemctl disable ${APP_NAME} 2>/dev/null || true
    rm -f /etc/systemd/system/${APP_NAME}.service; systemctl daemon-reload

    if [[ -d "${INSTALL_DIR}/data" ]]; then
        cp -r "${INSTALL_DIR}/data" "/tmp/${APP_NAME}-backup-$(date +%Y%m%d%H%M%S)" 2>/dev/null
    fi
    rm -rf "${INSTALL_DIR}"
    command -v firewall-cmd &>/dev/null && { firewall-cmd --remove-port=${PORT}/tcp --permanent 2>/dev/null; firewall-cmd --reload 2>/dev/null; }

    zenity --info --title="卸载完成" --text="卸载完成" --width=300
}

# ── CLI 安装 ──────────────────────────────
cli_install() {
    echo ""; echo "  管控平台 v${VERSION} 安装程序"; echo ""
    check_root
    [ -f /etc/os-release ] && . /etc/os-release
    info "系统: ${PRETTY_NAME:-Linux}"; info "目录: ${INSTALL_DIR}"; info "端口: ${PORT}"

    echo "[1/6] 检查环境..."
    if [[ $BIN_MODE -eq 0 ]]; then
        command -v python3 &>/dev/null || { warn "安装 python3..."; yum install -y python3 python3-pip 2>/dev/null || apt-get install -y python3 python3-pip 2>/dev/null || err "请手动安装 python3"; }
        log "Python3: $(python3 --version)"
    else
        log "二进制模式，无需 Python 环境"
    fi

    echo "[2/6] 安装依赖..."
    if [[ $BIN_MODE -eq 1 ]]; then
        log "二进制已内嵌，跳过"
    elif [[ -d "$SRC/deps" ]] && ls "$SRC/deps"/*.whl 2>/dev/null|head -1 >/dev/null; then
        info "离线模式"; pip3 install --no-index --find-links="$SRC/deps" flask paramiko apscheduler
    else
        pip3 install flask paramiko apscheduler -i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null || pip3 install flask paramiko apscheduler
    fi
    log "依赖就绪"

    echo "[3/6] 安装程序..."
    [[ -d "${INSTALL_DIR}" ]] && { warn "覆盖安装"; systemctl stop ${APP_NAME} 2>/dev/null || true; }
    mkdir -p "${INSTALL_DIR}/data"
    if [[ $BIN_MODE -eq 1 ]]; then
        cp "$SRC/oscar-monitor" "${INSTALL_DIR}/"
        chmod +x "${INSTALL_DIR}/oscar-monitor"
    else
        for f in app.py collector.py auth.py persist.py db_config.py requirements.txt; do
            [[ -f "$SRC/$f" ]] && cp "$SRC/$f" "${INSTALL_DIR}/"; done
        [[ -d "$SRC/static" ]] && cp -r "$SRC/static" "${INSTALL_DIR}/" 2>/dev/null
        [[ -d "$SRC/templates" ]] && cp -r "$SRC/templates" "${INSTALL_DIR}/" 2>/dev/null
    fi
    cp "$0" "${INSTALL_DIR}/" 2>/dev/null || true
    log "文件已复制"

    if [[ -f "${INSTALL_DIR}/data/config.json" ]]; then
        python3 -c "import json;c=json.load(open('${INSTALL_DIR}/data/config.json'));exit(0 if c.get('server_db_enabled') or c.get('log_enabled') else 1)" 2>/dev/null && {
            warn "检测到已配置数据库连接，数据可能丢失，建议先备份"
        }
    fi

    echo "[4/6] 重置数据..."
    rm -f "${INSTALL_DIR}/data/servers.json" "${INSTALL_DIR}/data/users.json" "${INSTALL_DIR}/data/config.json"
    log "数据目录已重置"

    echo "[5/6] 注册服务..."
    cat > /etc/systemd/system/${APP_NAME}.service << EOF
[Unit]
Description=管控平台 v${VERSION}
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${EXEC} --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload; systemctl enable ${APP_NAME}; systemctl start ${APP_NAME}
    sleep 2
    systemctl is-active --quiet ${APP_NAME} && log "服务已启动" || warn "检查: journalctl -u ${APP_NAME} -n 20"

    echo "[6/6] 防火墙..."
    command -v firewall-cmd &>/dev/null && { firewall-cmd --add-port=${PORT}/tcp --permanent 2>/dev/null; firewall-cmd --reload 2>/dev/null; log "已放行 ${PORT}"; }

    echo ""; echo "  安装完成  http://$(hostname -I | awk '{print $1}'):${PORT}"
    echo "  卸载: sudo ${INSTALL_DIR}/install.sh --uninstall"
}

# ── CLI 卸载 ──────────────────────────────
cli_uninstall() {
    check_root
    systemctl stop ${APP_NAME} 2>/dev/null || true; systemctl disable ${APP_NAME} 2>/dev/null || true
    rm -f /etc/systemd/system/${APP_NAME}.service; systemctl daemon-reload

    if [[ -d "${INSTALL_DIR}/data" ]]; then
        read -p "备份数据目录？(Y/n) " k; [[ ! "$k" =~ ^[nN] ]] && { cp -r "${INSTALL_DIR}/data" "/tmp/${APP_NAME}-backup-$(date +%Y%m%d%H%M%S)"; log "已备份"; }
    fi
    rm -rf "${INSTALL_DIR}"
    command -v firewall-cmd &>/dev/null && { firewall-cmd --remove-port=${PORT}/tcp --permanent 2>/dev/null; firewall-cmd --reload 2>/dev/null; }
    echo "  卸载完成"
}

# ── 入口 ──────────────────────────────────
if [[ $GUI -eq 1 ]] && [[ "$1" != "--cli" ]]; then
    ACTION=$(zenity --list --title="管控平台 v${VERSION}" --text="请选择操作" --column="操作" "安装" "卸载" "退出" --width=300 --height=200 2>/dev/null)
    case "$ACTION" in
        安装) gui_install ;;
        卸载) gui_uninstall ;;
        *) exit 0 ;;
    esac
else
    case "${1}" in
        --uninstall|-u) cli_uninstall ;;
        --help|-h)
            echo "用法: bash install.sh [选项]"
            echo "  无参数      安装 (有 GUI 则图形，无则命令行)"
            echo "  --cli       强制命令行安装"
            echo "  --uninstall 卸载"
            echo "  --help      帮助"
            ;;
        *) cli_install ;;
    esac
fi
