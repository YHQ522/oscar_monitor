"""用户模型与权限定义。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

PERMISSIONS: dict[str, str] = {
    "dashboard": "全局监控",
    "servers_view": "服务管理(查看)",
    "servers_edit": "服务管理(编辑)",
    "control_view": "启停管控(查看)",
    "control_exec": "启停管控(执行)",
    "admin": "系统管理",
}

ALL_PERMS = list(PERMISSIONS.keys())


class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    perms: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    perms: Optional[list[str]] = None
