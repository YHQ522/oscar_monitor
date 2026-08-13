# oscar-monitor 打包指南（免环境依赖）

将 **FastAPI 后端 + React 前端** 打包成可执行程序与安装包，目标机器无需安装
Python / Node.js 即可运行。

| 目标平台 | 产物 | 说明 |
|---|---|---|
| Windows | `build/dist/oscar-monitor-setup-2.0.0.exe` | **安装包**（Inno Setup，含卸载/快捷方式/开机自启） |
| Windows | `build/dist/oscar-monitor.exe` | 单文件 exe（绿色版，双击运行） |
| Linux | `build/dist/oscar-monitor`（单文件二进制） | 直接运行，或 |
| Linux | `build/dist/oscar-monitor-setup-<版本>-linux-x86_64.sh` | 自解压安装包，注册 systemd 服务 |

> 技术栈：PyInstaller（`--onefile`）+ Vite 前端构建产物内嵌；Windows 安装包用 Inno Setup 6。
> PyInstaller 不支持交叉编译：**Windows 产物必须在 Windows 上构建，Linux 产物必须在 Linux 上构建**。

## 目录结构

```
build/
├── oscar_monitor.spec   # PyInstaller 打包配置（Win/Linux 通用）
├── setup.iss            # Windows 安装包脚本（Inno Setup 6）
├── build_win.bat        # Windows 一键打包（exe + 安装包）
├── build_linux.sh       # Linux 一键打包（含自解压安装包）
├── install_linux.sh     # Linux 运行时安装脚本（安装到 /opt/oscar_monitor + systemd）
├── make_icon.py         # 生成 exe/安装包图标（需 pillow）
├── assets/              # 生成的应用图标（构建时自动生成）
├── build/               # PyInstaller 中间产物（可删除）
└── dist/                # 最终产物（exe + 安装包）
```

## 前置条件

- **Python 3.11+**（建议 3.11，PyInstaller 兼容性最好）
- **Node.js 18+**（构建前端）
- **Inno Setup 6**（仅 Windows 安装包需要：`winget install JRSoftware.InnoSetup`）
- 构建脚本会自动安装：后端依赖、`pyinstaller`、`pillow`

## Windows 打包

```bat
build\build_win.bat
```

脚本自动执行：构建前端 → 安装依赖 → 生成图标 → PyInstaller 打包 → Inno Setup
编译安装包（若已安装）。

**产物**：
- `build\dist\oscar-monitor-setup-2.0.0.exe` — 安装包（推荐分发）
- `build\dist\oscar-monitor.exe` — 单文件 exe（绿色版）

### 安装包特性

- 默认安装到 `C:\Program Files\OscarMonitor`（需管理员）
- 数据目录自动配置到 **`C:\ProgramData\OscarMonitor\data`**（运行时可写，
  通过环境变量 `OSCAR_DATA_DIR` 注入，卸载时自动清理）
- **安装时可指定监听端口**（向导端口页，或静默安装 `/Port=8080`），
  写入数据目录的 `config.json`（升级安装保留已有配置）
- 开始菜单 / 桌面快捷方式（可选）、开机自启（可选）、完整卸载（自动结束进程）
- 安装完成后可选立即启动

> 仅编译安装包（跳过 exe 打包，要求 exe 已存在）：
> ```bat
> "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /Qp build\setup.iss
> ```

**绿色版运行**：把 exe 拷贝到任意 Windows 机器（Win 10/11，x64），双击运行。
首次启动会在 exe 同级目录自动创建 `data/`。可选命令行参数：

```bat
oscar-monitor.exe --port 8080 --host 0.0.0.0
```

**注册为 Windows 服务**（可选）：用 NSSM 托管 exe，参考 `deploy/install_windows_service.bat`。

## 端口配置（编译后无需重新打包）

端口优先级：**命令行 `--port` > `config.json` 的 `port` > 环境变量 `OSCAR_PORT` > 5080**

| 场景 | 改法 |
|---|---|
| 绿色版 / 命令行 | `oscar-monitor.exe --port 8080` |
| 安装版（Win） | 数据目录 `config.json` 加 `"port": 8080`；或系统配置页「服务监听端口」（重启生效）；或快捷方式加 `--port 8080` |
| 安装版（Linux） | 编辑 `/opt/oscar_monitor/data/config.json` 的 `port` 后 `systemctl restart oscar-monitor` |
| 安装时指定 | Win 安装向导端口页 / `/Port=8080`；Linux 安装脚本交互提示 / `OSCAR_PORT=8080` |

前端用相对路径 `/api`，改端口后界面自动跟随，无需任何前端修改。

## Linux 打包

在 **Linux x86_64** 机器上执行：

```bash
bash build/build_linux.sh
```

脚本自动执行：构建前端 → 安装依赖 → PyInstaller 打包 → 生成自解压安装包。
产物：

```text
build/dist/oscar-monitor                                     # 单文件二进制
build/dist/oscar-monitor-setup-2.0.0-linux-x86_64.sh         # 自解压安装包
```

### 方式一：自解压安装包（推荐）

```bash
sudo bash build/dist/oscar-monitor-setup-2.0.0-linux-x86_64.sh
# 或指定端口（跳过交互提示）：sudo OSCAR_PORT=8080 bash ...setup.sh
```

安装到 `/opt/oscar_monitor`，注册 systemd 服务 `oscar-monitor`（开机自启、
崩溃自动重启），数据目录 `/opt/oscar_monitor/data`。
安装时会**交互提示输入端口**（写入 `data/config.json`；升级安装保留已有配置）。

```bash
systemctl status oscar-monitor      # 查看状态
systemctl restart oscar-monitor     # 重启
journalctl -u oscar-monitor -f      # 实时日志
```

### 方式二：单文件二进制直接运行

```bash
chmod +x build/dist/oscar-monitor
./build/dist/oscar-monitor --port 5080
```

数据目录默认创建在二进制同级 `data/` 下；也可用环境变量指定：
`OSCAR_DATA_DIR=/var/lib/oscar ./build/dist/oscar-monitor`。

## 常见问题

### 1. Linux 二进制在其他发行版跑不起来？

PyInstaller 产物依赖构建机的 glibc 版本。**为兼容旧系统，建议在较老的
发行版上构建**（如 CentOS 7 / Debian 10 / Ubuntu 20.04），这样生成的二进制
可以在更新的发行版上运行（反向不成立）。

### 2. exe 被杀毒软件误报？

PyInstaller 单文件打包常见误报。可：
- 使用 Windows Defender 添加信任；
- 或用 `upx=False`（本配置已默认关闭 UPX，降低误报概率）。

### 3. 前端改了代码，如何重新打包？

直接重新运行对应平台的打包脚本即可（会自动重新 `npm run build` 并打包）。

### 4. 手工构建步骤（不跑脚本）

```bash
# 1. 构建前端
cd frontend && npm ci && npm run build && cd ..

# 2. 安装依赖（Python 3.11）
cd backend && pip install -e . && pip install pyinstaller pillow && cd ..

# 3. 生成图标（可选）
python build/make_icon.py

# 4. PyInstaller 打包
cd build && python -m PyInstaller --noconfirm --clean oscar_monitor.spec
```
