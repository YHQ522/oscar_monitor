"""开发/生产启动入口：python run.py [--port 5080]"""
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="oscar-monitor 后端")
    parser.add_argument("--port", type=int, default=5080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
