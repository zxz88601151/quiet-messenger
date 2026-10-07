"""Phase 3C ConnectionManager 单元测试（不依赖网络）。

覆盖：register / remove / user→conns 映射 / device→conn 映射（顶替旧连接）/
      send_to_user 广播 / stale sweep 清理 / 事件信封结构。

用 asyncio.run 包装（不依赖 pytest-asyncio 插件）。
"""
from __future__ import annotations

import asyncio

from app.services.connection_manager import (
    ConnectionManager,
    ConnectionState,
    make_event,
)


class _FakeWS:
    """最小假 WebSocket，仅记录 send_json 调用。"""

    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, data):
        self.sent.append(data)


def test_register_and_remove():
    async def _run():
        mgr = ConnectionManager()
        ws = _FakeWS()
        conn = await mgr.register(ws, "u1", "dev-a")
        assert conn.conn_id.startswith("conn_")
        assert conn.state == ConnectionState.CONNECTED
        assert mgr.user_connection_count("u1") == 1
        assert mgr.get_device_connection("dev-a") is conn
        await mgr.remove(conn.conn_id)
        assert mgr.user_connection_count("u1") == 0
        assert mgr.get_device_connection("dev-a") is None

    asyncio.run(_run())


def test_same_device_replaces_old():
    async def _run():
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWS(), _FakeWS()
        c1 = await mgr.register(ws1, "u1", "dev-a")
        c2 = await mgr.register(ws2, "u1", "dev-a")
        # 新连接顶替旧连接（不重复 registry）
        assert mgr.get_device_connection("dev-a").conn_id == c2.conn_id
        assert mgr.user_connection_count("u1") == 1
        assert c1.state == ConnectionState.CLOSED

    asyncio.run(_run())


def test_send_to_user_broadcast():
    async def _run():
        mgr = ConnectionManager()
        ws1, ws2 = _FakeWS(), _FakeWS()
        await mgr.register(ws1, "u1", "dev-a")
        await mgr.register(ws2, "u1", "dev-b")
        n = await mgr.send_to_user("u1", make_event("connection.ping", {}))
        assert n == 2
        assert len(ws1.sent) == 1 and len(ws2.sent) == 1

    asyncio.run(_run())


def test_send_failure_cleans():
    async def _run():
        mgr = ConnectionManager()

        class _BrokenWS:
            async def send_json(self, data):
                raise RuntimeError("broken")

        c = await mgr.register(_BrokenWS(), "u1", "dev-x")
        ok = await mgr.send(c, make_event("connection.ping", {}))
        assert ok is False
        assert mgr.get(c.conn_id) is None

    asyncio.run(_run())


def test_stale_sweep():
    async def _run():
        mgr = ConnectionManager()
        ws = _FakeWS()
        c = await mgr.register(ws, "u1", "dev-s")
        from datetime import datetime, timedelta, timezone

        c.last_activity = (
            datetime.now(timezone.utc) - timedelta(seconds=120)
        ).isoformat()
        removed = await mgr.sweep_stale(timeout_seconds=60)
        assert removed >= 1
        assert mgr.get(c.conn_id) is None

    asyncio.run(_run())


def test_event_envelope_shape():
    evt = make_event("connection.ready", {"k": "v"})
    assert evt["type"] == "connection.ready"
    assert evt["id"].startswith("evt_")
    assert evt["timestamp"]
    assert evt["payload"] == {"k": "v"}
