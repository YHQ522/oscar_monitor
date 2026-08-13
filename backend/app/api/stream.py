"""SSE 实时推送路由 — 推送采集缓存变更。

支持两种认证：Authorization: Bearer <token>，或 ?token=<token>（EventSource 用）。
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings
from ..core.security import decode_token
from ..services.auth_service import UserService
from ..services.cache import CacheStore
from .deps import get_cache_dep, get_settings_dep, get_user_service_dep

router = APIRouter(prefix="/api", tags=["stream"])

_bearer = HTTPBearer(auto_error=False)


@router.get("/stream")
async def stream(
    request: Request,
    cache: CacheStore = Depends(get_cache_dep),
    settings: Settings = Depends(get_settings_dep),
    user_service: UserService = Depends(get_user_service_dep),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    token: str | None = Query(None),
):
    # 认证：header Bearer 或 query token 二选一
    token_str = token or (credentials.credentials if credentials else None)
    if not token_str:
        raise HTTPException(status_code=401, detail="未登录或会话已过期")
    payload = decode_token(token_str, settings.secret_key)
    if not payload or not payload.get("sub") or not user_service.get_user(payload["sub"]):
        raise HTTPException(status_code=401, detail="未登录或会话已过期")

    async def generate():
        last_seen: dict[str, str] = {}
        last_ping = 0.0
        sent_initial = False
        while True:
            if await request.is_disconnected():
                break
            now = asyncio.get_event_loop().time()
            snapshot = cache.snapshot()
            updates = {}
            if not sent_initial:
                # 首次连接：全量推送当前缓存，保证前端立即有数据
                updates = snapshot
                sent_initial = True
            else:
                for sid, data in snapshot.items():
                    ts = data.get("timestamp", "")
                    if ts != last_seen.get(sid):
                        last_seen[sid] = ts
                        updates[sid] = data
            if updates:
                yield f"data: {json.dumps(updates, ensure_ascii=False)}\n\n"
            # 心跳：每 15 秒发送注释行，防止代理/网络层因空闲断开
            elif now - last_ping >= 15:
                yield ": ping\n\n"
                last_ping = now
            await asyncio.sleep(2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
