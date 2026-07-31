"""SSH 连接与命令执行 — 独立底层，供采集/持久化/管控各层复用，消除循环依赖。"""
from __future__ import annotations

import re
import subprocess
from typing import Any

import paramiko

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def safe_decode(data: bytes | str) -> str:
    if isinstance(data, str):
        return data
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return str(data, errors="replace")


def need_ssh(server: dict[str, Any]) -> bool:
    host = server.get("ssh_host", "")
    return bool(host and host not in ("127.0.0.1", "localhost"))


def is_win(server: dict[str, Any]) -> bool:
    return server.get("os_type", "linux") == "windows"


def ssh_connect(server: dict[str, Any], timeout: float = 10) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=server.get("ssh_host"),
        port=server.get("ssh_port", 22),
        username=server.get("ssh_user", "root"),
        password=server.get("ssh_pass", ""),
        timeout=timeout,
    )
    return client


def ssh_exec(client: paramiko.SSHClient, cmd: str, timeout: float = 60) -> tuple[str, str, int]:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = safe_decode(stdout.read())
    err = safe_decode(stderr.read())
    ec = stdout.channel.recv_exit_status()
    return out, err, ec


def run_local(cmd: str, timeout: float = 30) -> tuple[str, str, int]:
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return proc.stdout, proc.stderr, proc.returncode


def translate_error(msg: str, error_map: dict[str, str], fix_map: dict[str, str] | None = None) -> str:
    """将底层错误信息翻译为中文提示，附修复建议。"""
    if not msg:
        return "未知错误"
    msg_lower = msg.lower()
    for key, chinese in error_map.items():
        if key in msg_lower:
            result = chinese
            if fix_map:
                fix = fix_map.get(key)
                if fix:
                    result += "\n修复建议: " + fix
            return result
    if msg:
        return "错误详情: " + msg[:200]
    return "未知错误"
