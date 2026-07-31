"""安全模块：PBKDF2 密码哈希 + JWT 令牌。"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

PBKDF2_ITERATIONS = 100_000
PBKDF2_PREFIX = "pbkdf2:"


def hash_password(pwd: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pwd.encode(), salt, PBKDF2_ITERATIONS)
    return PBKDF2_PREFIX + salt.hex() + ":" + dk.hex()


def verify_password(stored: str | None, password: str) -> bool:
    if not stored:
        return False
    if stored.startswith(PBKDF2_PREFIX):
        try:
            _, salt_hex, hash_hex = stored.split(":")
            salt = bytes.fromhex(salt_hex)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
            return dk.hex() == hash_hex
        except (ValueError, IndexError):
            return False
    # 旧版 SHA256 兼容
    return stored == hashlib.sha256(password.encode()).hexdigest()


def needs_upgrade(stored: str | None) -> bool:
    return bool(stored) and not stored.startswith(PBKDF2_PREFIX)


def create_token(payload: dict, secret: str, expire_minutes: int = 1800) -> str:
    now = datetime.now(timezone.utc)
    data = dict(payload)
    data["iat"] = now
    data["exp"] = now + timedelta(minutes=expire_minutes)
    return jwt.encode(data, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
