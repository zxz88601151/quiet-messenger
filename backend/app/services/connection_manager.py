"""WebSocket Connection Manager（Phase 3C 基础设施）。

职责（仅基础设施，不含聊天/好友/会话等业务事件）：
- 注册 / 移除连接（Connection Registry）
- user_id → 多个 Connection 映射（单用户多设备）
- device_id → Connection 映射
- 发送事件到指定连接 / 指定用户（广播）
- 连接生命周期状态（CONNECTING / AUTHENTICATING / CONNECTED / CLOSING / CLOSED）
- 心跳活动跟踪（last_activity）供 stale 清理

不实现：message.new / friend.* / conversation.* / handoff.*（留后续 Phase）。

事件信封（统一 §13）：
    { "type": str, "id": str, "timestamp": str, "payload": dict }
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import WebSocket

from app.config import get_settings

settings = get_settings()


class ConnectionState(str, Enum):
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    CLOSING = "closing"
    CLOSED = "closed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_event(event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """构造统一事件信封（§13）。"""
    return {
        "type": event_type,
        "id": f"evt_{uuid.uuid4().hex[:16]}",
        "timestamp": _now_iso(),
        "payload": payload or {},
    }


class Connection:
    """单条 WebSocket 连接的内部表示。"""

    def __init__(self, conn_id: str, websocket: WebSocket) -> None:
        self.conn_id = conn_id
        self.websocket = websocket
        self.user_id: str | None = None
        self.device_id: str | None = None
        self.state: ConnectionState = ConnectionState.AUTHENTICATING
        self.connected_at = _now_iso()
        self.last_activity = _now_iso()

    def touch(self) -> None:
        self.last_activity = _now_iso()

    def is_stale(self, timeout_seconds: int) -> bool:
        """距上次活动超过阈值即判定 stale（heartbeat §16）。"""
        try:
            last = datetime.fromisoformat(self.last_activity)
        except (ValueError, TypeError):
            return False
        delta = (datetime.now(timezone.utc) - last).total_seconds()
        return delta > timeout_seconds


class ConnectionManager:
    """进程内连接注册表（单实例，由 lifespan / module 持有）。

    注意：FastAPI 单进程内有效；多 worker / 多实例需外接 Redis pub/sub（Phase 5+）。
    本 Phase 3C 仅单进程基础设施验证。
    """

    def __init__(self) -> None:
        self._conns: dict[str, Connection] = {}
        self._user_to_conns: dict[str, set[str]] = {}
        self._device_to_conn: dict[str, str] = {}
        self._lock = asyncio.Lock()

    # ---- 注册 / 移除 ----
    async def register(
        self, websocket: WebSocket, user_id: str, device_id: str | None
    ) -> Connection:
        async with self._lock:
            conn = Connection(conn_id=f"conn_{uuid.uuid4().hex[:12]}", websocket=websocket)
            conn.user_id = user_id
            conn.device_id = device_id
            conn.state = ConnectionState.CONNECTED
            conn.touch()
            # 同一 device 新连接顶替旧的（避免重复 registry）：先清理旧连接映射。
            if device_id:
                old = self._device_to_conn.get(device_id)
                if old and old in self._conns:
                    self._conns[old].state = ConnectionState.CLOSED
                    self._user_to_conns.get(user_id, set()).discard(old)
                    del self._conns[old]
                self._device_to_conn[device_id] = conn.conn_id
            self._conns[conn.conn_id] = conn
            self._user_to_conns.setdefault(user_id, set()).add(conn.conn_id)
            return conn

    async def remove(self, conn_id: str) -> None:
        async with self._lock:
            conn = self._conns.pop(conn_id, None)
            if conn is None:
                return
            conn.state = ConnectionState.CLOSED
            if conn.user_id and conn.user_id in self._user_to_conns:
                self._user_to_conns[conn.user_id].discard(conn_id)
                if not self._user_to_conns[conn.user_id]:
                    del self._user_to_conns[conn.user_id]
            if conn.device_id and self._device_to_conn.get(conn.device_id) == conn_id:
                del self._device_to_conn[conn.device_id]

    # ---- 查询 ----
    def get(self, conn_id: str) -> Connection | None:
        return self._conns.get(conn_id)

    def get_user_connections(self, user_id: str) -> list[Connection]:
        ids = self._user_to_conns.get(user_id, set())
        return [self._conns[c] for c in ids if c in self._conns]

    def get_device_connection(self, device_id: str) -> Connection | None:
        cid = self._device_to_conn.get(device_id)
        return self._conns.get(cid) if cid else None

    def count(self) -> int:
        return len(self._conns)

    def user_connection_count(self, user_id: str) -> int:
        return len(self._user_to_conns.get(user_id, set()))

    async def close_all_user_devices(self, user_id: str) -> int:
        """S-1：关闭该用户全部 live WS 连接（如改密后强制下线）。

        返回实际关闭的连接数；单条关闭失败不影响其余。
        """
        conns = self.get_user_connections(user_id)
        closed = 0
        for conn in conns:
            try:
                await conn.websocket.close(code=4401)
                closed += 1
            except Exception:
                pass
            await self.remove(conn.conn_id)
        return closed

    # ---- 发送 ----
    async def send(self, conn: Connection, event: dict[str, Any]) -> bool:
        """发送到单连接。失败（断连）返回 False 并清理。"""
        try:
            await conn.websocket.send_json(event)
            conn.touch()
            return True
        except Exception:
            await self.remove(conn.conn_id)
            return False

    async def send_to_user(self, user_id: str, event: dict[str, Any]) -> int:
        """广播到某用户所有连接。返回成功数。"""
        sent = 0
        for conn in self.get_user_connections(user_id):
            if await self.send(conn, event):
                sent += 1
        return sent

    async def send_to_device(self, device_id: str, event: dict[str, Any]) -> bool:
        conn = self.get_device_connection(device_id)
        if conn is None:
            return False
        return await self.send(conn, event)

    # ---- stale 清理（heartbeat §16）----
    async def sweep_stale(self, timeout_seconds: int | None = None) -> int:
        """清理超时无活动的连接，返回清理数。"""
        timeout = timeout_seconds or settings.WS_HEARTBEAT_TIMEOUT_SECONDS
        to_remove: list[str] = []
        for cid, conn in self._conns.items():
            if conn.state in (ConnectionState.CLOSED, ConnectionState.CLOSING):
                to_remove.append(cid)
            elif conn.is_stale(timeout):
                to_remove.append(cid)
        for cid in to_remove:
            await self.remove(cid)
        return len(to_remove)


# 全局单例（单进程）。多 worker 部署需外部共享层（Phase 5+）。
manager = ConnectionManager()
