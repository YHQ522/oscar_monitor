"""服务器配置模型。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    name: str = ""
    port: int = 0
    svc_name: str = ""
    svc_mgr: str = "systemctl"
    in_control: bool = True
    group: str = "其他应用"
    start_cmd: str = ""
    stop_cmd: str = ""
    status_cmd: str = ""


class ServerBase(BaseModel):
    name: str
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = "root"
    ssh_pass: str = ""
    db_host: str = "127.0.0.1"
    db_port: int = 2003
    db_user: str = "SYSDBA"
    db_pass: str = ""
    db_name: str = "OSRDB"
    db_type: str = "oscar"
    isql_cmd: str = "isql"
    auto_refresh: int = 0
    os_type: str = "linux"
    in_control: bool = True
    persist_enabled: bool = False
    svc_name: str = ""
    svc_mgr: str = "systemctl"
    svc_start_cmd: str = ""
    svc_stop_cmd: str = ""
    # None = 未提供（创建时填充默认）；[] = 用户显式选择（如“仅系统”/“仅数据库”），必须尊重
    enabled_categories: Optional[list[str]] = None
    enabled_os_checks: Optional[list[str]] = None
    skip_db: bool = False  # 仅系统监控：跳过数据库采集/连接测试
    apps: list[AppConfig] = Field(default_factory=list)
    # 数据库错误日志（elog）采集：路径（目录/通配/逗号分隔，留空全盘搜索）+ 时间窗（小时）
    elog_path: str = ""
    elog_hours: int = 24


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    name: Optional[str] = None
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    ssh_pass: Optional[str] = None
    db_host: Optional[str] = None
    db_port: Optional[int] = None
    db_user: Optional[str] = None
    db_pass: Optional[str] = None
    db_name: Optional[str] = None
    db_type: Optional[str] = None
    isql_cmd: Optional[str] = None
    auto_refresh: Optional[int] = None
    os_type: Optional[str] = None
    in_control: Optional[bool] = None
    persist_enabled: Optional[bool] = None
    svc_name: Optional[str] = None
    svc_mgr: Optional[str] = None
    svc_start_cmd: Optional[str] = None
    svc_stop_cmd: Optional[str] = None
    enabled_categories: Optional[list[str]] = None
    enabled_os_checks: Optional[list[str]] = None
    skip_db: Optional[bool] = None
    apps: Optional[list[AppConfig]] = None
    elog_path: Optional[str] = None
    elog_hours: Optional[int] = None


class ServerOut(BaseModel):
    """对外输出，脱敏密码字段。"""

    id: str
    name: str
    ssh_host: str = ""
    ssh_port: int = 22
    ssh_user: str = ""
    db_host: str = ""
    db_port: int = 2003
    db_user: str = ""
    db_name: str = ""
    db_type: str = "oscar"
    isql_cmd: str = "isql"
    auto_refresh: int = 0
    os_type: str = "linux"
    in_control: bool = True
    persist_enabled: bool = False
    svc_name: str = ""
    svc_mgr: str = "systemctl"
    svc_start_cmd: str = ""
    svc_stop_cmd: str = ""
    enabled_categories: list[str] = Field(default_factory=list)
    enabled_os_checks: list[str] = Field(default_factory=list)
    skip_db: bool = False
    apps: list[dict[str, Any]] = Field(default_factory=list)
    elog_path: str = ""
    elog_hours: int = 24
    has_ssh_pass: bool = False
    has_db_pass: bool = False
    created_at: Optional[str] = None

    @classmethod
    def from_server(cls, server: dict[str, Any]) -> "ServerOut":
        data = {k: v for k, v in server.items() if k not in ("ssh_pass", "db_pass")}
        data["has_ssh_pass"] = bool(server.get("ssh_pass"))
        data["has_db_pass"] = bool(server.get("db_pass"))
        return cls(**data)
