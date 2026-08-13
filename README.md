# oscar-monitor 数据库监控管控平台（v2 重构版）

基于 SSH/CLI 的多数据库监控管控平台，支持 **Oscar(神通) / MySQL / PostgreSQL / Oracle**。
全栈重构版：**FastAPI + React(Vite+TS)**，分层清晰、可测试、可扩展。

> 旧版平铺式代码（`app.py` / `collector.py` 等）已归档到 `legacy/` 目录，仅作功能参考与回退；新架构位于 `backend/` 与 `frontend/`。

## 目录结构

```
oscar_monitor/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用工厂 + 生命周期（启动/关闭调度器）
│   │   ├── config.py           # pydantic-settings 配置（兼容旧 data/config.json）
│   │   ├── core/               # 基础层（无业务依赖）
│   │   │   ├── ssh.py          #   SSH 连接 / 命令执行 / 错误翻译
│   │   │   ├── db_exec.py      #   CLI SQL 构建 / 执行 / 输出解析
│   │   │   ├── security.py     #   PBKDF2 密码哈希 + JWT
│   │   │   ├── rate_limit.py   #   登录限速
│   │   │   └── constants.py    #   OS 检查 / 标签 / 错误映射
│   │   ├── adapters/           # 数据库适配器（新增数据库 = 新建子类注册）
│   │   │   ├── base.py         #   DBAdapter 抽象（DDL 方言 / CLI / SQL 函数）
│   │   │   └── oscar|mysql|postgresql|oracle.py
│   │   ├── repositories/       # 数据仓储（可拔插）
│   │   │   ├── __init__.py     #   接口 + 工厂（json | sqlite）
│   │   │   ├── json_repos.py   #   JSON 文件实现（默认，兼容旧数据）
│   │   │   └── sql_repos.py    #   SQLAlchemy(SQLite) 实现
│   │   ├── services/           # 业务层（依赖 core + repositories）
│   │   │   ├── collector.py    #   采集 / 连接测试 / 启停管控
│   │   │   ├── scheduler.py    #   定时采集调度 + 线程池
│   │   │   ├── health.py       #   健康评分 + 指标解析（单一事实来源）
│   │   │   ├── trend.py        #   趋势历史存储
│   │   │   ├── persist.py      #   日志持久化（错误/慢SQL）
│   │   │   ├── export_service.py # Excel/CSV 导出
│   │   │   ├── auth_service.py #   认证 / 用户管理
│   │   │   ├── server_service.py# 服务器 CRUD
│   │   │   └── config_service.py# 系统配置读写
│   │   └── api/                # 路由层（BluePrint 风格 Router）
│   │       ├── deps.py         #   依赖注入 + JWT 认证 + 权限
│   │       └── auth|servers|control|config|reports|sql_terminal|stream.py
│   ├── tests/                  # pytest（26 项：认证/权限/CRUD/解析/评分）
│   ├── pyproject.toml          # uv 项目管理（含清华镜像源）
│   └── run.py                  # 启动入口
├── frontend/                   # React 前端
│   ├── public/                 # 静态资源（favicon 等）
│   ├── src/
│   │   ├── api/                #   fetch 封装 + 类型定义
│   │   ├── store/auth.ts       #   zustand 认证状态
│   │   ├── hooks/useSSE.ts     #   SSE 实时推送
│   │   ├── components/         #   Layout / QueryTable
│   │   └── pages/              #   11 个页面（路由级懒加载）
│   ├── package.json
│   └── vite.config.ts          # dev 代理 /api → 5080（含 vendor 分包）
├── legacy/                     # 旧版 Flask 代码（归档，仅参考）
├── data/                       # 数据目录（与旧版共用，平滑迁移）
├── deploy/                     # 生产部署（systemd / nginx / Windows 服务 / 指南）
└── README.md
```

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + Pydantic v2 + APScheduler + paramiko + openpyxl + SQLAlchemy |
| 前端 | React 18 + Vite + TypeScript + antd + zustand + recharts |
| 依赖管理 | 后端 uv / 前端 npm |
| 认证 | JWT（Bearer）+ PBKDF2 密码哈希 + IP 登录限速 |

## 快速启动

### 1. 后端（Python ≥ 3.11）

```bash
cd backend
uv sync                 # 已配置清华镜像源，国内可直接安装
uv run python run.py --port 5080
# 或直接
python run.py
```

启动后 API 文档：http://127.0.0.1:5080/docs

### 2. 前端（Node ≥ 18）

```bash
cd frontend
npm install
npm run dev             # http://localhost:5173（已代理 /api 到 5080）
```

### 3. 生产部署

```bash
cd frontend && npm run build   # 产物输出到 frontend/dist
cd ../backend && python run.py # 后端自动托管 dist 静态资源
```

## 配置说明

- 环境变量前缀 `OSCAR_`（如 `OSCAR_STORAGE_BACKEND=sqlite` 切换数据存储后端）
- 数据目录默认 `data/`，与旧版共用 `servers.json` / `users.json` / `config.json`，**无需迁移即可复用现有数据**
- 默认管理员：`admin / admin123`（首次启动自动创建，请及时修改）

## 测试

```bash
cd backend
uv run pytest          # 26 项测试全部通过
```

## 免环境打包（安装包 / exe）

无需目标机器安装 Python / Node，PyInstaller 把「后端 + 前端产物」打成单文件，
Windows 再用 Inno Setup 封装成正式安装包：

| 平台 | 命令 | 产物 |
|---|---|---|
| Windows | `build\build_win.bat` | `build\dist\oscar-monitor-setup-2.0.0.exe`（**安装包**）+ 单文件 exe |
| Linux | `bash build/build_linux.sh` | `build/dist/oscar-monitor` + 自解压安装包 `.sh`（systemd 托管） |

Windows 安装包特性：管理员安装、**安装时可指定端口**（向导端口页 / `/Port=` 参数）、
数据目录自动配置到 `C:\ProgramData\OscarMonitor\data`（运行时可写）、
快捷方式/开机自启可选、完整卸载（自动清理环境变量与进程）。
端口优先级：命令行 `--port` > `config.json` 的 `port` > 环境变量 `OSCAR_PORT` > 5080。

详见 [`build/README_BUILD.md`](build/README_BUILD.md)。

## 与旧版的关键差异

| 维度 | 旧版 | v2 |
|---|---|---|
| 后端框架 | Flask + 单文件 app.py(1430行) | FastAPI + 分层包 |
| 数据访问 | 模块级全局 dict + 手动锁 | 仓储模式（JSON/SQLite 可拔插） |
| 认证 | Session + Cookie | JWT + 限速器独立模块 |
| 前端 | 模板内嵌 JS | React 组件化 + 类型安全 |
| 循环依赖 | collector ↔ persist ↔ db_config ↔ auth | 统一依赖 core/adapters 底层 |
| 测试 | 无 | pytest 26 项 |

## 扩展指南

- **新增数据库类型**：在 `backend/app/adapters/` 新建子类（继承 `DBAdapter`），定义 DDL 方言与查询集，然后在 `adapters/__init__.py` 注册。
- **新增监控指标**：在对应适配器的 `query_sets` 增加查询；如需参与健康评分/趋势，同步更新 `services/health.py`。
- **切换数据存储**：启动时设 `OSCAR_STORAGE_BACKEND=sqlite` 即用 SQLite；`repositories/` 已抽象接口，可再加 PostgreSQL/MySQL 实现。
