"""WebSocket 实时层 Endpoint（Phase 3C 基础设施）。

路径：/ws/v1（版本化、最小稳定；记录进 API_CONTRACT §10）。
鉴权：原生客户端优先在握手时携带 `Authorization: Bearer <access_token>` 头
      （Dart/websockets 均支持自定义头）。**禁止把 token 放进 URL query**（§8 安全红线）。
      缺失/无效/过期令牌 → 拒绝连接（close code 4401），不进入业务事件。
认证成功后发送：connection.authenticated → connection.ready（§15）。

事件信封（§13/§14）：
   Server→Client: connection.authenticated / connection.ready / connection.ping / connection.error
   Client→Server: connection.auth / connection.pong / connection.close

本文件仅基础设施，**不实现任何业务事件**（message.* / friend.* / conversation.* / handoff.*）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.config import get_settings
from app.core import security
from app.db.base import SessionLocal
from app.services.connection_manager import (
    ConnectionState,
    make_event,
    manager,
)
from app.services.presence import presence

settings = get_settings()
router = APIRouter(prefix="/ws/v1", tags=["realtime"])


def _auth_from_headers(websocket: WebSocket) -> tuple[str, str | None] | None:
    """从握手请求头取 Bearer access token。

    返回 (user_id, device_id) 或 None（无/无效令牌）。
    """
    auth = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth[len("bearer ") :].strip()
    try:
        payload = security.decode_token(token, security.TOKEN_TYPE_ACCESS)
    except Exception:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    return str(user_id), payload.get("device_id")


async def _close_with_error(websocket: WebSocket, code: int, msg: str) -> None:
    try:
        await websocket.send_json(
            make_event("connection.error", {"code": "WS_AUTH_FAILED", "message": msg})
        )
    except Exception:
        pass
    await websocket.close(code=code)


@router.websocket("")
async def ws_connect(websocket: WebSocket) -> None:
    """统一 WebSocket 入口（/ws/v1）。

    流程：accept → 读 Bearer 头鉴权 → 失败 close(4401) → 成功注册 →
          connection.authenticated + connection.ready → 心跳 + 消息循环 → 清理。
    """
    await websocket.accept()
    auth_result = _auth_from_headers(websocket)
    if auth_result is None:
        await _close_with_error(websocket, code=4401, msg="缺少或无效的认证令牌")
        return

    user_id, device_id = auth_result
    # device_id 可能为空（纯 access token 无 device claim）→ 用 user 维度兜底标识。
    effective_device = device_id or f"user-{user_id}"

    conn = await manager.register(websocket, user_id, effective_device)
    # 新连接接入时顺带清理一次 stale（heartbeat §16：避免 stale 永不清理）。
    asyncio.create_task(manager.sweep_stale())
    # Presence: notify friends that this user came online (first connection).
    try:
        with SessionLocal() as db:
            await presence.on_connect(user_id, db)
    except Exception:
        pass  # Presence notification failure must not break the WS connection.
    try:
        # 鉴权成功通知（§14 Server→Client）。
        await manager.send(conn, make_event("connection.authenticated", {
            "user_id": user_id,
            "device_id": effective_device,
        }))
        # 连接就绪（§15）：客户端收到后置 CONNECTED。
        await manager.send(conn, make_event("connection.ready", {
            "connection_id": conn.conn_id,
            "user_id": user_id,
            "device_id": effective_device,
            "user_connection_count": manager.user_connection_count(user_id),
        }))

        # Initial Presence Sync: send current online state of all friends.
        # Without this, already-online friends show as offline until they
        # disconnect/reconnect (Initial Presence Sync Gap).
        try:
            with SessionLocal() as db:
                online_friends = presence.get_online_friend_ids(user_id, db)
                for fid in online_friends:
                    await manager.send(conn, make_event("presence.update", {
                        "user_id": fid,
                        "status": "online",
                        "initial": True,
                    }))
        except Exception:
            pass  # Initial presence sync failure must not break WS connection.

        # 心跳 + 入站消息并发循环（§16）。
        ping_task = asyncio.create_task(_heartbeat_loop(conn, websocket))
        recv_task = asyncio.create_task(_receive_loop(conn, websocket))
        done, pending = await asyncio.wait(
            {ping_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.remove(conn.conn_id)
        # Presence: notify friends if this user's last connection closed.
        try:
            with SessionLocal() as db:
                await presence.on_disconnect(user_id, db)
        except Exception:
            pass


async def _heartbeat_loop(conn: Any, websocket: WebSocket) -> None:
    """服务端周期发送 connection.ping（应用层），客户端须回 connection.pong（§16）。"""
    try:
        while True:
            await asyncio.sleep(settings.WS_HEARTBEAT_INTERVAL_SECONDS)
            ok = await manager.send(conn, make_event("connection.ping", {}))
            if not ok:
                return
    except asyncio.CancelledError:
        return


async def _receive_loop(conn: Any, websocket: WebSocket) -> None:
    """监听客户端消息：connection.pong / connection.close / 未知帧忽略（不执行业务）。"""
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                etype = msg.get("type")
            except (json.JSONDecodeError, AttributeError):
                # 非法帧不处理，也不执行业务事件（§27：未认证不执行业务）。
                continue
            if etype == "connection.pong":
                conn.touch()
            elif etype == "connection.close":
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                return
            else:
                # 基础设施阶段忽略任何业务事件类型（防御性，不抛错）。
                continue
    except WebSocketDisconnect:
        return
