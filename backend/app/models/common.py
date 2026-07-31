"""通用响应模型。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class OkResp(BaseModel):
    status: str = "ok"
    msg: str = ""
    data: Optional[Any] = None


class ErrResp(BaseModel):
    status: str = "error"
    msg: str = ""


class ApiError(Exception):
    """业务异常，由全局异常处理器统一转为 JSON。"""

    def __init__(self, status_code: int, msg: str, extra: dict | None = None):
        self.status_code = status_code
        self.msg = msg
        self.extra = extra or {}
