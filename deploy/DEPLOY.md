# oscar-monitor 生产部署指南

本文档介绍将平台部署到生产环境的完整流程：Linux（systemd + nginx + HTTPS）与 Windows（NSSM 服务）。

## 0. 构建前端

```bash
cd frontend
npm ci            # 或 npm install
npm run build     # 产物输出到 frontend/dist，由后端 FastAPI 直接托管
```

> 生产模式无需单独启动 Vite dev server；后端会自动托管 `frontend/dist` 并处理 SPA 路由回退。

## 1. Linux 部署（推荐）

### 1.1 准备

```bash
# 安装依赖
cd backend
uv sync --no-dev
cd ..

# 创建运行用户（非 root）
sudo useradd -r -s /usr/sbin/nologin oscar
sudo mkdir -p /opt/oscar_monitor
sudo chown -R oscar:oscar /opt/oscar_monitor
# 将项目代码放到 /opt/oscar_monitor 下（backend/ frontend/ data/）
```

### 1.2 生成密钥

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# 输出如 8f3a...（保存下来，写入下面的环境变量）
```

### 1.3 systemd 服务

编辑 `deploy/oscar-monitor.service`，替换：

- `WorkingDirectory` / `ExecStart` 中的路径为实际路径
- `OSCAR_SECRET_KEY` 为上一步生成的随机串

```bash
sudo cp deploy/oscar-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oscar-monitor
sudo systemctl status oscar-monitor
```

验证：`curl http://127.0.0.1:5080/api/meta` 应返回 JSON。

### 1.4 nginx 反代 + HTTPS

1. 安装 nginx，并将域名解析到服务器
2. 申请证书（certbot）：`sudo certbot certonly --nginx -d monitor.example.com`
3. 复制 `deploy/nginx.conf.example` 到 `/etc/nginx/conf.d/oscar-monitor.conf`，替换域名为你的域名
4. `sudo nginx -t && sudo systemctl reload nginx`

### 1.5 常用运维

```bash
sudo journalctl -u oscar-monitor -f          # 实时日志
sudo systemctl restart oscar-monitor         # 重启
# 数据备份：data/ 目录（servers.json / users.json / config.json / reports/）
sudo tar czf backup_$(date +%F).tar.gz data/
```

## 2. Windows 部署

### 2.1 准备

```bat
cd backend
uv sync --no-dev
cd ..\frontend
npm ci && npm run build
```

### 2.2 注册为服务（NSSM）

1. 下载 [NSSM](https://nssm.cc/download)，将 `nssm.exe` 加入 PATH
2. 双击运行 `deploy\install_windows_service.bat`
3. 服务名为 `oscar-monitor`，开机自启

### 2.3 生产密钥

在 Windows 服务中注入环境变量（NSSM）：

```bat
nssm set oscar-monitor AppEnvironmentExtra OSCAR_SECRET_KEY=8f3a...（随机串）
```

### 2.4 反向代理（可选）

Windows 下可用 IIS ARR 或 Caddy 反代 `127.0.0.1:5080`。若用 nginx for Windows，参考 `deploy/nginx.conf.example`（SSE 需 `proxy_buffering off`）。

## 3. 生产安全清单

- [ ] `OSCAR_SECRET_KEY` 已设置为 ≥32 字节随机值（默认值仅用于开发）
- [ ] 前端已 `npm run build`（不使用 dev server）
- [ ] 通过 HTTPS 访问（SSE 需要）
- [ ] 修改默认 admin 密码
- [ ] 定期备份 `data/` 目录
- [ ] 若启用告警通知，在「系统配置 → 告警通知」配置并点击「保存并发送测试通知」验证
- [ ] 视规模调整 `OSCAR_COLLECT_WORKERS`（默认 8，最大 32）

## 4. 环境变量参考

| 变量 | 默认 | 说明 |
|---|---|---|
| `OSCAR_SECRET_KEY` | 开发默认值 | JWT 签名密钥，生产必改 |
| `OSCAR_STORAGE_BACKEND` | `json` | `json` / `sqlite` |
| `OSCAR_COLLECT_WORKERS` | `8` | 并发采集线程数（1-32） |
| `OSCAR_AUTO_COLLECT_INTERVAL` | `30` | 自动采集间隔（秒） |
| `OSCAR_SSH_CONNECT_TIMEOUT` | `10` | SSH 连接超时（秒） |
| `OSCAR_SSH_EXEC_TIMEOUT` | `120` | SQL 命令超时（秒） |
| `OSCAR_TREND_RETENTION_DAYS` | `7` | 趋势历史保留天数 |
| `OSCAR_NOTIFY_ENABLED` | `false` | 启用告警通知（也可在配置页设置） |
