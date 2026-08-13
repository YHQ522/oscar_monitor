"""开发/生产启动入口：python run.py [--port 5080]

端口优先级：命令行 --port > config.json 的 port > 环境变量 OSCAR_PORT > 5080。

同时兼容 PyInstaller 冻结打包（--onefile）：
- 直接传入 app 对象启动 uvicorn，避免按字符串导入模块在冻结环境下的兼容问题
- 冻结模式下自动禁用 --reload（源码热重载不适用于打包产物）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _resolve_port(cli_port: int | None) -> int:
    """CLI 未显式指定端口时，从配置（OSCAR_PORT 环境变量 / config.json）读取。"""
    if cli_port is not None:
        return cli_port
    from app.config import get_settings

    return int(get_settings().port)


def main() -> None:
    parser = argparse.ArgumentParser(description="oscar-monitor 后端")
    parser.add_argument("--port", type=int, default=None, help="监听端口（缺省时读取配置/环境变量，默认 5080）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    # 冻结（PyInstaller）环境下，工作目录可能不含 app 包，显式加入 sys.path
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        if str(meipass) not in sys.path:
            sys.path.insert(0, str(meipass))
        if args.reload:
            print("提示：冻结模式下不支持 --reload，已忽略。")
            args.reload = False

    import uvicorn

    from app.main import app

    port = _resolve_port(args.port)
    if not (1 <= port <= 65535):
        print(f"[错误] 端口号无效：{port}（应在 1-65535 之间）")
        sys.exit(1)

    uvicorn.run(
        app,
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
