"""认证路由：登录/登出/当前用户/用户管理/IP 封禁管理。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..core.rate_limit import LoginRateLimiter, get_login_limiter
from ..core.security import create_token
from ..models.user import PERMISSIONS, UserCreate, UserUpdate
from ..services.auth_service import UserService
from .deps import (
    any_permission,
    get_client_ip,
    get_current_user,
    get_settings_dep,
    get_user_service_dep,
    require_permission,
)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginForm(BaseModel):
    username: str
    password: str


class ChangePwdForm(BaseModel):
    old_password: str
    new_password: str


def _public(user: dict) -> dict:
    return {k: v for k, v in user.items() if k != "password"}


@router.post("/auth/login")
def login(
    form: LoginForm,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    user_service: UserService = Depends(get_user_service_dep),
    limiter: LoginRateLimiter = Depends(get_login_limiter),
):
    ip = get_client_ip(request)
    # 先查用户（不验证密码）以决定是否 admin 豁免
    pre_user = user_service.get_user(form.username)
    is_admin = bool(pre_user and pre_user.get("is_admin"))

    # 限速检查先于密码哈希（防止暴力尝试烧 CPU）；admin 豁免
    if not is_admin:
        remaining = limiter.check(ip)
        if remaining > 0:
            limiter.set_username(ip, form.username)
            raise HTTPException(status_code=429, detail=f"登录失败次数过多，请 {remaining} 分钟后再试")

    user = user_service.check_login(form.username, form.password)
    if user:
        limiter.clear(ip)
        token = create_token({"sub": user["username"]}, settings.secret_key, settings.token_expire_minutes)
        return {"token": token, "user": _public(user)}

    limiter.record_failure(ip)
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.post("/auth/logout")
def logout():
    return {"status": "ok"}


@router.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return _public(user)


@router.put("/auth/password")
def change_password(
    form: ChangePwdForm,
    user: dict = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service_dep),
):
    ok, msg = user_service.change_password(user["username"], form.old_password, form.new_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "msg": msg}


# ═══════════════ 用户管理（admin） ═══════════════
@router.get("/users", dependencies=[Depends(require_permission("admin"))])
def list_users(user_service: UserService = Depends(get_user_service_dep)):
    return user_service.list_users()


@router.post("/users", dependencies=[Depends(require_permission("admin"))])
def add_user(
    data: UserCreate,
    user_service: UserService = Depends(get_user_service_dep),
):
    ok, msg = user_service.add_user(data.username, data.password, data.is_admin, data.perms)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "msg": msg}


@router.put("/users/{username}", dependencies=[Depends(require_permission("admin"))])
def update_user(
    username: str,
    data: UserUpdate,
    user_service: UserService = Depends(get_user_service_dep),
):
    ok, msg = user_service.update_user(username, data.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "msg": msg}


@router.delete("/users/{username}", dependencies=[Depends(require_permission("admin"))])
def delete_user(username: str, user_service: UserService = Depends(get_user_service_dep)):
    ok, msg = user_service.delete_user(username)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "ok", "msg": msg}


@router.get("/permissions", dependencies=[Depends(require_permission("admin"))])
def permissions():
    return PERMISSIONS


# ═══════════════ IP 封禁管理（admin） ═══════════════
@router.get("/admin/locked-ips", dependencies=[Depends(require_permission("admin"))])
def locked_ips(limiter: LoginRateLimiter = Depends(get_login_limiter)):
    return {"locked": limiter.locked_list()}


@router.post("/admin/unlock-ip", dependencies=[Depends(require_permission("admin"))])
def unlock_ip(data: dict, limiter: LoginRateLimiter = Depends(get_login_limiter)):
    ip = (data.get("ip") or "").strip()
    if not ip:
        raise HTTPException(status_code=400, detail="IP 不能为空")
    limiter.unlock(ip)
    return {"ok": True, "msg": f"已解锁 {ip}"}
