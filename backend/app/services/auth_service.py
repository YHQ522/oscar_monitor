"""认证与用户管理服务 — 依赖 UserRepository，带 60s 缓存。"""
from __future__ import annotations

import time
from typing import Any

from ..config import Settings
from ..core.security import hash_password, needs_upgrade, verify_password
from ..models.user import ALL_PERMS, PERMISSIONS, User
from ..repositories import UserRepository


_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    """固定假哈希：用户不存在时也执行一次同成本校验，抹平响应时序差（防用户名枚举）。"""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("oscar-dummy-timing-credential")
    return _DUMMY_HASH


class UserService:
    def __init__(self, repo: UserRepository, settings: Settings):
        self.repo = repo
        self.settings = settings
        self._cache: list[dict[str, Any]] | None = None
        self._cache_time = 0.0

    def _load(self) -> list[dict[str, Any]]:
        now = time.time()
        if self._cache is not None and now - self._cache_time < 60:
            return self._cache
        users = self.repo.list()
        if not users:
            users = [{
                "username": "admin",
                "password": hash_password("admin123"),
                "is_admin": True,
                "perms": ALL_PERMS,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }]
            self.repo.save_all(users)
        self._cache = users
        self._cache_time = now
        return users

    def invalidate(self) -> None:
        self._cache = None
        self._cache_time = 0

    # ── 查询 ──
    def list_users(self) -> list[dict[str, Any]]:
        return [{k: v for k, v in u.items() if k != "password"} for u in self._load()]

    def get_user(self, username: str) -> dict[str, Any] | None:
        return next((u for u in self._load() if u.get("username") == username), None)

    def check_login(self, username: str, password: str) -> dict[str, Any] | None:
        user = self.get_user(username)
        if user and verify_password(user.get("password"), password):
            # 旧版哈希升级为 PBKDF2
            if needs_upgrade(user.get("password")):
                user["password"] = hash_password(password)
                self._save_user(user)
            return user
        # 用户不存在时也执行一次同成本校验，抹平响应时序差（防用户名枚举）
        if not user:
            verify_password(password, _dummy_hash())
        return None

    # ── 变更 ──
    def _save_user(self, user: dict[str, Any]) -> None:
        users = self._load()
        users = [u if u.get("username") != user.get("username") else user for u in users]
        self.repo.save_all(users)
        self.invalidate()

    def change_password(self, username: str, old_pwd: str, new_pwd: str) -> tuple[bool, str]:
        user = self.get_user(username)
        if not user:
            return False, "用户不存在"
        if not verify_password(user.get("password"), old_pwd):
            return False, "原密码错误"
        if not new_pwd or len(new_pwd) < 6:
            return False, "新密码长度至少 6 位"
        user["password"] = hash_password(new_pwd)
        self._save_user(user)
        return True, "密码修改成功"

    def add_user(self, username: str, password: str, is_admin: bool, perms: list[str]) -> tuple[bool, str]:
        username = username.strip()
        if not username:
            return False, "用户名不能为空"
        if self.get_user(username):
            return False, "用户已存在"
        if not password or len(password) < 6:
            return False, "密码长度至少 6 位"
        if is_admin:
            perms = ALL_PERMS
        user = {
            "username": username,
            "password": hash_password(password),
            "is_admin": is_admin,
            "perms": [p for p in perms if p in PERMISSIONS],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        users = self._load() + [user]
        self.repo.save_all(users)
        self.invalidate()
        return True, "用户创建成功"

    def update_user(self, username: str, data: dict[str, Any]) -> tuple[bool, str]:
        user = self.get_user(username)
        if not user:
            return False, "用户不存在"
        if "password" in data and data["password"]:
            if len(data["password"]) < 6:
                return False, "密码长度至少 6 位"
            user["password"] = hash_password(data["password"])
        if "is_admin" in data:
            user["is_admin"] = bool(data["is_admin"])
        if "perms" in data:
            user["perms"] = [p for p in data["perms"] if p in PERMISSIONS]
        if user.get("is_admin"):
            user["perms"] = ALL_PERMS
        self._save_user(user)
        return True, "用户更新成功"

    def delete_user(self, username: str) -> tuple[bool, str]:
        if username == "admin":
            return False, "不能删除内置 admin 用户"
        user = self.get_user(username)
        if not user:
            return False, "用户不存在"
        users = [u for u in self._load() if u.get("username") != username]
        self.repo.save_all(users)
        self.invalidate()
        return True, "用户删除成功"


_user_service: UserService | None = None


def get_user_service(settings: Settings) -> UserService:
    global _user_service
    if _user_service is None:
        from ..repositories import get_user_repo

        _user_service = UserService(get_user_repo(settings), settings)
    return _user_service
