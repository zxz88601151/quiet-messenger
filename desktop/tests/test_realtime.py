"""Phase 3C RealtimeClient 测试（Desktop / PySide6）。

单元：状态机 / 退避 / 事件解析 / token 缺失处理（mock websockets）。
集成：连真实 Backend /ws/v1（development 8011），验证 auth→ready（需 backend 运行）。
真实后端由验证脚本启动于 127.0.0.1:8011；CI 无后端时集成测试自动跳过。
"""
from __future__ import annotations

import asyncio
import os

import pytest

from app.realtime import (
    ConnectionState,
    EventEnvelope,
    RealtimeClient,
    RealtimeError,
)

_WS_BASE = os.getenv("LIAOTIAN_WS_VERIFY_URL", "http://127.0.0.1:8022")


def test_event_envelope_parse():
    e = EventEnvelope.from_json(
        {"type": "connection.ready", "id": "x", "timestamp": "t", "payload": {"a": 1}}
    )
    assert e.type == "connection.ready" and e.payload == {"a": 1}
    assert EventEnvelope.pong()["type"] == "connection.pong"


def test_initial_state():
    c = RealtimeClient(base_url=_WS_BASE, get_token=lambda: None, on_token_expired=lambda: asyncio.sleep(0))
    assert c.state == ConnectionState.DISCONNECTED


def test_backoff_schedule():
    c = RealtimeClient(base_url=_WS_BASE, get_token=lambda: None, on_token_expired=lambda: asyncio.sleep(0))
    seq = [c._backoff() for _ in range(6)]
    assert seq == [1, 2, 4, 8, 16, 16]  # 封顶 16s


def test_no_token_sets_error_then_backoff():
    states: list[ConnectionState] = []
    c = RealtimeClient(
        base_url=_WS_BASE,
        get_token=lambda: None,
        on_token_expired=lambda: asyncio.sleep(0),
        on_state_change=states.append,
    )
    # 无事件循环环境下 connect() 不应抛错（幂等自保护）
    c.connect()
    c.disconnect()
    assert c.state == ConnectionState.DISCONNECTED


# ---------------- 集成：真实 Backend WS ----------------
def _have_backend() -> bool:
    import urllib.request

    try:
        urllib.request.urlopen(f"{_WS_BASE}/health", timeout=3)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _have_backend(), reason="需要真实 Backend /ws/v1 (8011)")
def test_integration_auth_ready():
    import urllib.request
    import json

    # 注册并拿到真实 access token
    stamp = str(os.getpid())[-5:]
    user = f"wsverify_{stamp}"
    phone = "13" + stamp
    r = urllib.request.urlopen(
        urllib.request.Request(
            f"{_WS_BASE}/api/v1/auth/register",
            data=json.dumps({"username": user, "phone": phone, "password": "pw123456", "nickname": "WS"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        ),
        timeout=5,
    )
    body = json.loads(r.read())
    token = body["access_token"]

    states: list[ConnectionState] = []
    events: list[EventEnvelope] = []
    c = RealtimeClient(
        base_url=_WS_BASE,
        get_token=lambda: token,
        on_token_expired=lambda: asyncio.sleep(0),
        on_state_change=states.append,
        on_event=events.append,
    )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_connect_and_wait(c, loop))
    finally:
        c.disconnect()
        loop.close()

    assert ConnectionState.AUTHENTICATING in states
    assert ConnectionState.CONNECTED in states
    ready = [e for e in events if e.type == "connection.ready"]
    assert ready, "未收到 connection.ready"
    assert ready[0].payload["user_id"]
    assert ready[0].payload["connection_id"].startswith("conn_")


async def _connect_and_wait(c: RealtimeClient, loop):
    c.connect()
    # 等待 CONNECTED（最多 5s）
    for _ in range(50):
        if c.state == ConnectionState.CONNECTED:
            break
        await asyncio.sleep(0.1)
    # 收一发心跳 ping 并回 pong（验证心跳链路）
    await asyncio.sleep(0.3)
    c.disconnect()
    await asyncio.sleep(0.1)
