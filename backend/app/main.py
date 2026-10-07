"""V1.1 Backend 应用入口（Phase 2B Auth + 2C REST + 2D 就绪性 + 3C WS 基础设施）。

已实现：GET /health + Auth + User + Friend + Conversation/Message + Device REST + WebSocket(/ws/v1)。
严格不实现：聊天消息业务 / 好友实时事件 / QR Desktop Login 流程（Phase 6）/ E2EE / Handoff / Space。
  （WebSocket 仅作实时传输通道基础设施；message.*/friend.*/conversation.*/handoff.* 属后续 Phase。）
契约事实源：shared/DATA_MODEL.md / API_CONTRACT.md / STATE_MACHINES.md / V1.1_SCOPE.md
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.errors import error_response, validation_error
from app.routers import auth, users, friends, conversations, devices
from app.routers import ws as ws_router
from app.services.connection_manager import manager


async def http_exception_handler(request: Request, exc: HTTPException):
    """统一错误格式（API_CONTRACT §7）：{ "error": { code, message, status } }。

    FastAPI 默认把 detail 包成 {"detail": ...}，这里扁平化为契约要求结构。
    """
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response("ERROR", str(detail), exc.status_code).detail,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 校验失败 → 统一 400 VALIDATION_ERROR（API_CONTRACT §7，第 86-90 行）。

    FastAPI 默认返回 422，但契约将"校验错误"统一定义为 400 VALIDATION_ERROR，
    因此在此扁平化为契约结构，避免客户端出现 400/422 两套语义。
    """
    # 提取首个错误原因，保持 message 可读但不泄露字段枚举细节。
    msg = "请求参数校验失败"
    try:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", []))
        if loc:
            msg = f"字段校验失败：{loc}"
    except Exception:
        pass
    return JSONResponse(
        status_code=400,
        content=validation_error(msg).detail,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # 生产环境必须有 JWT_SECRET（不实现流程，仅配置校验，避免明文提交）。
    if settings.is_production and not settings.JWT_SECRET:
        raise RuntimeError(
            "ENVIRONMENT=production 但 JWT_SECRET 未配置。请通过环境变量注入密钥，禁止硬编码。"
        )
    # DEF-RT-009: background periodic stale-connection cleanup. Without this,
    # dead connections are only swept when a NEW connection arrives — a server
    # with no new connections would retain stale sockets indefinitely.
    cleanup_task = asyncio.create_task(_stale_connection_sweep())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


async def _stale_connection_sweep() -> None:
    """Periodically sweep stale WebSocket connections (DEF-RT-009)."""
    settings = get_settings()
    interval = settings.WS_CLEANUP_INTERVAL_SECONDS
    while True:
        try:
            await asyncio.sleep(interval)
            removed = await manager.sweep_stale()
            if removed:
                import logging
                logging.getLogger("liaotian.ws").info("swept %d stale connections", removed)
        except asyncio.CancelledError:
            break
        except Exception:
            # Sweep must never crash the app; log and continue.
            import logging
            logging.getLogger("liaotian.ws").exception("stale sweep failed")


app = FastAPI(
    title="Minimal Chat API",
    version="1.1.0",
    description="极简私人通讯 V1.1 Backend（Phase 2B Auth + 2C REST + 2D 就绪性）",
    lifespan=lifespan,
)

# CORS（Phase 2D Staging 就绪性）：由环境变量 CORS_ORIGINS 控制，逗号分隔。
# 原生客户端（Flutter/PySide6）走 httpx/Dio 不受 CORS 限制；此中间件为 Web/Admin/未来表面预留。
# 默认仅放行本机 Staging 常用源；生产应显式设置具体域名，禁止留空通配。
_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(friends.router)
app.include_router(conversations.router)
app.include_router(devices.router)
app.include_router(ws_router.router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """基础健康检查。返回最小稳定结构，不扩展业务。"""
    return {"status": "ok", "service": "minimal-chat", "phase": "2D"}
