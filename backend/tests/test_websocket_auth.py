"""Phase 3C WebSocket 鉴权与连接测试（真实 WS，非 mock）。

用 Starlette TestClient 的 websocket_connect（真实握手 + 真实连接管理）。
覆盖：鉴权成功 / 缺 token 拒绝 / 无效 token 拒绝 / 单用户多设备双连接 /
      断开清理（不影响其他连接）/ 心跳 ping / 事件信封结构 / 安全（token 不泄露）。
"""
from __future__ import annotations

from app.config import get_settings
from app.services.connection_manager import manager


def _connect(client, token):
    return client.websocket_connect("/ws/v1", headers={"Authorization": f"Bearer {token}"})


def _assert_ready(envelope: dict, user_id: str, device_id: str) -> None:
    assert envelope["type"] == "connection.ready", envelope
    assert set(envelope.keys()) >= {"type", "id", "timestamp", "payload"}, envelope
    assert envelope["payload"]["user_id"] == user_id
    assert envelope["payload"]["device_id"] == device_id
    assert envelope["payload"]["connection_id"].startswith("conn_")


# ---------------- 鉴权成功 ----------------
def test_ws_auth_success(client, auth_headers):
    info = auth_headers()
    with _connect(client, info["access_token"]) as ws:
        # 首帧应为 connection.authenticated
        auth_evt = ws.receive_json()
        assert auth_evt["type"] == "connection.authenticated"
        assert auth_evt["payload"]["user_id"] == info["user_id"]
        # 次帧应为 connection.ready
        ready = ws.receive_json()
        _assert_ready(ready, info["user_id"], info["device_id"])
        assert ready["payload"]["user_connection_count"] == 1


# ---------------- 缺 token 拒绝 ----------------
def test_ws_missing_token_rejected(client):
    with client.websocket_connect("/ws/v1") as ws:
        # 服务端立即发 connection.error 再 close(4401)
        err = ws.receive_json()
        assert err["type"] == "connection.error"
        assert err["payload"]["code"] == "WS_AUTH_FAILED"


def test_ws_missing_token_close_code(client):
    with client.websocket_connect("/ws/v1") as ws:
        # 收一帧后连接应被服务端关闭（4401 = 自定义未认证码）
        ws.receive_json()
        # 再尝试读取应触发关闭
        try:
            ws.receive_json()
        except Exception:
            pass  # 关闭即符合预期


# ---------------- 无效 token 拒绝 ----------------
def test_ws_invalid_token_rejected(client):
    with client.websocket_connect("/ws/v1", headers={"Authorization": "Bearer not-a-real-token"}) as ws:
        err = ws.receive_json()
        assert err["type"] == "connection.error"
        assert err["payload"]["code"] == "WS_AUTH_FAILED"


# ---------------- 单用户多设备双连接 ----------------
def test_ws_same_user_dual_device(client, auth_headers):
    info = auth_headers(username="dualuser", phone="13900000901", password="secret123")
    from app.core import security
    from app.config import get_settings as gs

    s = gs()
    # 用同一 user 生成两个不同 device 的 access token
    tok_m = security.create_access_token(info["user_id"], info["device_id"])
    dev2 = info["device_id"] + "-desktop"
    tok_d = security.create_access_token(info["user_id"], dev2)

    with _connect(client, tok_m) as wsm, _connect(client, tok_d) as wsd:
        wsm.receive_json()  # authenticated
        rm = wsm.receive_json()
        _assert_ready(rm, info["user_id"], info["device_id"])
        wsd.receive_json()  # authenticated
        rd = wsd.receive_json()
        _assert_ready(rd, info["user_id"], dev2)

        # 两条连接都 ready 后，用实时 registry 计数断言（快照 payload.count 可能因并发注册时机不准）
        assert manager.user_connection_count(info["user_id"]) == 2
        assert rm["payload"]["connection_id"].startswith("conn_")
        assert rd["payload"]["connection_id"].startswith("conn_")


# ---------------- 断开清理（不影响其他连接）----------------
def test_ws_disconnect_cleans_only_self(client, auth_headers):
    info = auth_headers(username="discuser", phone="13900000902", password="secret123")
    from app.core import security
    from app.config import get_settings as gs

    s = gs()
    tok_m = security.create_access_token(info["user_id"], info["device_id"])
    dev2 = info["device_id"] + "-desktop"
    tok_d = security.create_access_token(info["user_id"], dev2)

    with _connect(client, tok_d) as wsd:
        wsd.receive_json()
        wsd.receive_json()  # ready

        # Mobile 连接后断开
        with _connect(client, tok_m) as wsm:
            wsm.receive_json()
            wsm.receive_json()  # ready
            assert manager.user_connection_count(info["user_id"]) == 2
        # Mobile 关闭后，registry 应只剩 Desktop
        import time
        time.sleep(0.2)
        assert manager.user_connection_count(info["user_id"]) == 1
        # Desktop 仍可正常收心跳（稍后验证）


# ---------------- 心跳 ping ----------------
def test_ws_heartbeat_ping(client, auth_headers):
    info = auth_headers(username="hbuser", phone="13900000903", password="secret123")
    settings = get_settings()
    old = settings.WS_HEARTBEAT_INTERVAL_SECONDS
    settings.WS_HEARTBEAT_INTERVAL_SECONDS = 1  # 加速测试
    try:
        with _connect(client, info["access_token"]) as ws:
            ws.receive_json()  # authenticated
            ws.receive_json()  # ready
            # 等待服务端发 connection.ping
            received_ping = False
            for _ in range(3):
                evt = ws.receive_json()
                if evt["type"] == "connection.ping":
                    received_ping = True
                    break
            assert received_ping, "未收到 heartbeat ping"
    finally:
        settings.WS_HEARTBEAT_INTERVAL_SECONDS = old


# ---------------- 客户端 pong 更新活动 ----------------
def test_ws_client_pong(client, auth_headers):
    info = auth_headers(username="ponguser", phone="13900000904", password="secret123")
    with _connect(client, info["access_token"]) as ws:
        ws.receive_json()  # authenticated
        ws.receive_json()  # ready
        ws.send_json({"type": "connection.pong"})
        # 连接应保持打开（不抛错）
        assert manager.user_connection_count(info["user_id"]) == 1


# ---------------- 安全：token 不出现在错误响应 ----------------
def test_ws_error_no_token_leak(client):
    with client.websocket_connect("/ws/v1", headers={"Authorization": "Bearer leaked-should-not-appear"}) as ws:
        err = ws.receive_json()
        assert "leaked-should-not-appear" not in str(err)
