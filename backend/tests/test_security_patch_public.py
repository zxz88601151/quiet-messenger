"""公开版安全补丁回归测试（S-1 / S-2 / H-1 / H-3）。

- S-1：reset-password 成功后，旧 refresh token 立即失效（401）。
- S-2：forgot-password 限流（5/10min/IP+phone）；reset code 连错 10 次作废。
- H-1：refresh 轮换复用检测 — 宽限内重试放行；logout 后复用熔断 family。
- H-3：WS 未认证连接在 accept 前被拒绝；握手限流 20/分钟/IP。
"""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


def _register(client, username, phone, password="secret123"):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "phone": phone, "password": password,
              "nickname": username},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _forgot_dev_code(client, phone):
    r = client.post("/api/v1/auth/forgot-password", json={"phone": phone})
    assert r.status_code == 200, r.text
    return r.json().get("dev_code")


# ---------------- S-1 ----------------
def test_s1_reset_password_revokes_old_refresh(client):
    body = _register(client, "s1user", "13600000001")
    old_refresh = body["refresh_token"]

    code = _forgot_dev_code(client, "13600000001")
    assert code, "dev 模式应返回 dev_code"
    r = client.post(
        "/api/v1/auth/reset-password",
        json={"phone": "13600000001", "code": code, "new_password": "newsecret123"},
    )
    assert r.status_code == 200, r.text

    # 旧 refresh token 必须立即失效
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401, r2.text

    # 新密码可正常登录
    r3 = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "13600000001",
            "password": "newsecret123",
            "device": {"device_type": "mobile", "device_name": "S1Test"},
        },
    )
    assert r3.status_code == 200, r3.text


# ---------------- S-2 ----------------
def test_s2_forgot_password_rate_limited(client):
    _register(client, "s2user", "13600000002")
    statuses = [
        client.post("/api/v1/auth/forgot-password", json={"phone": "13600000002"}).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
    assert client.post(
        "/api/v1/auth/forgot-password", json={"phone": "13600000002"}
    ).json()["error"]["code"] == "RATE_LIMITED"


def test_s2_reset_code_invalidated_after_10_failures(client):
    _register(client, "s2buser", "13600000003")
    code = _forgot_dev_code(client, "13600000003")
    assert code
    # 10 次输错 → code 作废；第 11 次用正确 code 也必须失败
    for _ in range(10):
        r = client.post(
            "/api/v1/auth/reset-password",
            json={"phone": "13600000003", "code": "000000", "new_password": "newsecret123"},
        )
        assert r.status_code == 400, r.text
    r = client.post(
        "/api/v1/auth/reset-password",
        json={"phone": "13600000003", "code": code, "new_password": "newsecret123"},
    )
    assert r.status_code == 400  # code 已被作废


# ---------------- H-1 ----------------
def test_h1_reuse_within_grace_treated_as_retry(client):
    body = _register(client, "h1user", "13600000004")
    old_refresh = body["refresh_token"]

    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r1.status_code == 200, r1.text
    new_refresh = r1.json()["refresh_token"]
    assert new_refresh != old_refresh

    # 宽限内重放旧 token（模拟客户端超时重试）→ 视为合法重试，放行
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 200, r2.text
    assert r2.json()["refresh_token"] not in (old_refresh, new_refresh)


def test_h1_reuse_after_logout_burns_family(client):
    body = _register(client, "h1buser", "13600000005")
    tok_a = body["refresh_token"]

    r1 = client.post("/api/v1/auth/refresh", json={"refresh_token": tok_a})
    assert r1.status_code == 200
    tok_b = r1.json()["refresh_token"]

    # logout（设备吊销路径）→ 复用无宽限
    assert client.post("/api/v1/auth/logout", json={"refresh_token": tok_b}).status_code == 200

    # 重放已吊销的 tok_b → 401，且整个 family 被熔断
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": tok_b})
    assert r2.status_code == 401, r2.text

    # family 内其他 token 同样失效（即使之前轮换出的也一并熔断）
    r3 = client.post("/api/v1/auth/refresh", json={"refresh_token": tok_a})
    assert r3.status_code == 401


# ---------------- H-3 ----------------
def test_h3_ws_handshake_rate_limited(client, auth_headers):
    info = auth_headers(username="h3user", phone="13600000006")
    token = info["access_token"]
    ok = 0
    rejected = 0
    for _ in range(21):
        try:
            with client.websocket_connect(
                "/ws/v1", headers={"Authorization": f"Bearer {token}"}
            ):
                ok += 1
        except WebSocketDisconnect:
            rejected += 1
    assert ok == 20
    assert rejected == 1
