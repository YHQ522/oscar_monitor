"""系统配置路由：读取/更新配置、测试日志库连接。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings
from ..core.constants import DB_ERROR_TRANSLATE, SSH_ERROR_TRANSLATE, SSH_FIX_LINUX, SSH_FIX_WIN
from ..core.db_exec import exec_sql
from ..core.ssh import translate_error
from ..services.scheduler import CollectScheduler
from ..services.auth_service import UserService
from .deps import get_config_service_dep, get_scheduler_dep, get_settings_dep, get_user_service_dep, require_permission

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config", dependencies=[Depends(require_permission("admin"))])
def get_config(config_service=Depends(get_config_service_dep)):
    return config_service.get()


@router.put("/config", dependencies=[Depends(require_permission("admin"))])
def update_config(
    data: dict,
    config_service=Depends(get_config_service_dep),
    scheduler: CollectScheduler = Depends(get_scheduler_dep),
    user_service: UserService = Depends(get_user_service_dep),
):
    result = config_service.update(data)
    scheduler.reinit()
    user_service.invalidate()
    return result


@router.post("/config/test-notify", dependencies=[Depends(require_permission("admin"))])
def test_notify(settings: Settings = Depends(get_settings_dep)):
    """发送一条测试告警通知，验证 Webhook / 邮件渠道可用性。"""
    from ..services.notify import get_notifier

    return get_notifier(settings).send_test()


@router.post("/config/test-log-db", dependencies=[Depends(require_permission("admin"))])
def test_log_db(data: dict):
    result: dict = {"ssh": None, "db": None}
    ssh_host = data.get("ssh_host", "")

    if ssh_host and ssh_host not in ("127.0.0.1", "localhost"):
        try:
            from ..core.ssh import ssh_connect

            client = ssh_connect({
                "ssh_host": ssh_host,
                "ssh_port": data.get("ssh_port", 22),
                "ssh_user": data.get("ssh_user", "root"),
                "ssh_pass": data.get("ssh_pass", ""),
            })
            client.close()
            result["ssh"] = {"ok": True, "msg": "SSH连接成功"}
        except Exception as e:  # noqa: BLE001
            # 修复建议按 SSH 目标系统判断（此处 ssh_host 必非本地）
            fix_map = SSH_FIX_WIN if str(data.get("os_type", "")).lower() == "windows" else SSH_FIX_LINUX
            result["ssh"] = {"ok": False, "msg": translate_error(str(e), SSH_ERROR_TRANSLATE, fix_map)}
            return result

    server_cfg = {
        "db_host": data.get("host", "127.0.0.1"),
        "db_port": data.get("port", 2003),
        "db_user": data.get("user", "SYSDBA"),
        "db_pass": data.get("pass", ""),
        "db_name": data.get("dbname", "OSRDB"),
        "db_type": data.get("db_type", "oscar"),
        "isql_cmd": data.get("isql", "isql"),
        "ssh_host": data.get("ssh_host", ""),
        "ssh_port": data.get("ssh_port", 22),
        "ssh_user": data.get("ssh_user", "root"),
        "ssh_pass": data.get("ssh_pass", ""),
        "os_type": "linux",
    }
    try:
        out, err, ec = exec_sql(server_cfg, "select 1;", timeout=15)
        if ec != 0 and not out.strip():
            raise RuntimeError(err or "执行失败")
        result["db"] = {"ok": True, "msg": "数据库连接成功"}
    except Exception as e:  # noqa: BLE001
        result["db"] = {"ok": False, "msg": translate_error(str(e), DB_ERROR_TRANSLATE)}
    return result
