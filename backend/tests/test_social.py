"""V1.1 Phase 2C 社交数据面测试。

覆盖：User(me/patch/search) / Friend(requests/accept/reject/list/delete) /
Conversation(list/detail) / Message(paginate/send+幂等/越权403) / Device(GET/DELETE-revoke)。

鉴权：所有端点需 Bearer（无 token → 401）。
越权：非会话成员访问会话 → 403；非好友发消息 → 403 FRIEND_REQUIRED。
幂等：相同 client_message_id → 返回已存消息。
范围：不测试 WS 推送（Phase 5）/ QR（Phase 6）。
"""
from __future__ import annotations

import pytest


def _register(client, username, phone, password="secret123"):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "phone": phone, "password": password, "nickname": username.title()},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, identifier, password="secret123", device_type="mobile"):
    r = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password, "device": {"device_type": device_type}},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------- User ----------------
def test_get_me_returns_privacy(client, auth_headers):
    tok = auth_headers()["access_token"]
    r = client.get("/api/v1/users/me", headers=_auth_headers(tok))
    assert r.status_code == 200
    b = r.json()
    assert "password_hash" not in b
    ps = b["privacy_settings"]
    assert set(ps.keys()) == {
        "read_receipt_enabled",
        "online_status_visibility",
        "typing_indicator_enabled",
        "new_device_login_alert",
        "message_retention",
    }


def test_patch_me_nickname_and_privacy(client, auth_headers):
    creds = auth_headers()
    tok = creds["access_token"]
    r = client.patch(
        "/api/v1/users/me",
        headers=_auth_headers(tok),
        json={"nickname": "NewName", "privacy_settings": {"online_status_visibility": "none"}},
    )
    assert r.status_code == 200
    b = r.json()
    assert b["nickname"] == "NewName"
    assert b["privacy_settings"]["online_status_visibility"] == "none"
    # merge patch：未提交的键保持默认
    assert b["privacy_settings"]["read_receipt_enabled"] is True


def test_patch_me_rejects_unknown_privacy_key(client, auth_headers):
    tok = auth_headers()["access_token"]
    r = client.patch(
        "/api/v1/users/me",
        headers=_auth_headers(tok),
        json={"privacy_settings": {"evil_key": True}},
    )
    assert r.status_code == 400


def test_patch_me_rejects_bad_visibility_value(client, auth_headers):
    tok = auth_headers()["access_token"]
    r = client.patch(
        "/api/v1/users/me",
        headers=_auth_headers(tok),
        json={"privacy_settings": {"online_status_visibility": "some_friends"}},
    )
    assert r.status_code == 400


def test_search_user_by_username(client, auth_headers):
    bob = auth_headers()  # 注册 bob 一次
    _register(client, "alice2", "13800000099")
    r = client.get("/api/v1/users/search?q=alice2", headers=_auth_headers(bob["access_token"]))
    assert r.status_code == 200
    assert any(u["username"] == "alice2" for u in r.json())


def test_search_requires_auth(client):
    r = client.get("/api/v1/users/search?q=x")
    assert r.status_code == 401


# ---------------- Friend ----------------
def test_friend_request_and_accept_flow(client, auth_headers):
    _register(client, "frank", "13700000101")
    bob = auth_headers()  # bob
    # bob 发请求给 frank
    r = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "frank"},
    )
    assert r.status_code == 201, r.text
    req_id = r.json()["id"]

    # frank 登录后接受
    frank = _login(client, "frank")
    acc = client.post(
        f"/api/v1/friends/requests/{req_id}/accept",
        headers=_auth_headers(frank["access_token"]),
    )
    assert acc.status_code == 200
    assert "friendship" in acc.json() and "conversation" in acc.json()
    # 双方好友列表都有对方
    bf = client.get("/api/v1/friends", headers=_auth_headers(bob["access_token"])).json()
    ff = client.get("/api/v1/friends", headers=_auth_headers(frank["access_token"])).json()
    assert any(u["user"]["username"] == "frank" for u in bf)
    assert any(u["user"]["username"] == "bob" for u in ff)


def test_friend_request_duplicate(client, auth_headers):
    _register(client, "dave", "13700000102")
    bob = auth_headers()
    p = {"target_username_or_phone": "dave"}
    r1 = client.post("/api/v1/friends/requests", headers=_auth_headers(bob["access_token"]), json=p)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/friends/requests", headers=_auth_headers(bob["access_token"]), json=p)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DUPLICATE_REQUEST"


def test_friend_request_self_rejected(client, auth_headers):
    bob = auth_headers()
    r = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "bob"},
    )
    assert r.status_code == 400


def test_friend_request_nonexistent(client, auth_headers):
    bob = auth_headers()
    r = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "nobody123"},
    )
    assert r.status_code == 404


def test_friend_reject_flow(client, auth_headers):
    _register(client, "erin", "13700000103")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "erin"},
    ).json()
    erin = _login(client, "erin")
    rj = client.post(
        f"/api/v1/friends/requests/{req['id']}/reject",
        headers=_auth_headers(erin["access_token"]),
    )
    assert rj.status_code == 200 and rj.json().get("ok") is True
    # 再次 accept 应冲突（已 rejected）
    acc = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(erin["access_token"]),
    )
    assert acc.status_code == 409


def test_friend_request_resend_after_reject(client, auth_headers):
    """回归测试 DEF-BE-001：rejected 后重新发送请求应重新激活（200），而非 500。"""
    _register(client, "helen", "13700000105")
    bob = auth_headers()
    # 第一次发送 → 201
    r1 = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "helen"},
    )
    assert r1.status_code == 201
    req_id = r1.json()["id"]
    # helen 拒绝
    helen = _login(client, "helen")
    rj = client.post(
        f"/api/v1/friends/requests/{req_id}/reject",
        headers=_auth_headers(helen["access_token"]),
    )
    assert rj.status_code == 200
    # bob 重新发送同一请求 → 应重新激活（不能 500），router 固定返回 201
    r2 = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "helen"},
    )
    assert r2.status_code in (200, 201), f"重新发送请求失败: {r2.status_code} {r2.text}"
    assert r2.json()["status"] == "pending"
    assert r2.json()["id"] == req_id  # 同一行被重新激活，不是新建


def test_friend_accept_requires_receiver(client, auth_headers):
    _register(client, "gary", "13700000104")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "gary"},
    ).json()
    # bob（sender）尝试 accept → 404（仅 receiver 可操作）
    acc = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(bob["access_token"]),
    )
    assert acc.status_code == 404


def test_delete_friend_keeps_messages(client, auth_headers):
    _register(client, "heidi", "13700000105")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "heidi"},
    ).json()
    heidi = _login(client, "heidi")
    conv = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(heidi["access_token"]),
    ).json()["conversation"]
    # bob 发一条消息
    msg = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers=_auth_headers(bob["access_token"]),
        json={"content": "hi", "client_message_id": "cm-1"},
    )
    assert msg.status_code == 201
    # bob 删除好友
    delr = client.delete(
        f"/api/v1/friends/{heidi['user']['id']}",
        headers=_auth_headers(bob["access_token"]),
    )
    assert delr.status_code == 200 and delr.json().get("ok") is True
    # 删除后 bob 再发消息 → 403 FRIEND_REQUIRED
    msg2 = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers=_auth_headers(bob["access_token"]),
        json={"content": "after delete", "client_message_id": "cm-2"},
    )
    assert msg2.status_code == 403
    assert msg2.json()["error"]["code"] == "FRIEND_REQUIRED"
    # 历史消息仍在（GET messages 仍可拉，因为 bob 仍是会话 member）
    hist = client.get(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers=_auth_headers(bob["access_token"]),
    )
    assert hist.status_code == 200
    assert len(hist.json()["items"]) == 1


# ---------------- Conversation / Message ----------------
def test_conversation_list_and_send(client, auth_headers):
    _register(client, "ivan", "13700000106")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "ivan"},
    ).json()
    ivan = _login(client, "ivan")
    conv = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(ivan["access_token"]),
    ).json()["conversation"]

    # bob 发消息
    m = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers=_auth_headers(bob["access_token"]),
        json={"content": "hello ivan", "client_message_id": "c1"},
    )
    assert m.status_code == 201
    assert m.json()["content"] == "hello ivan"
    assert m.json()["sender_id"] == bob["user_id"]

    # 会话列表含该会话 + last_message + unread_count(ivan 未读)
    cl = client.get("/api/v1/conversations", headers=_auth_headers(bob["access_token"])).json()
    assert len(cl) == 1
    assert cl[0]["last_message"]["content"] == "hello ivan"
    # ivan 视角 unread=1
    cli = client.get("/api/v1/conversations", headers=_auth_headers(ivan["access_token"])).json()
    assert cli[0]["unread_count"] == 1


def test_message_idempotent(client, auth_headers):
    _register(client, "judy", "13700000107")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "judy"},
    ).json()
    judy = _login(client, "judy")
    conv = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(judy["access_token"]),
    ).json()["conversation"]
    m1 = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers=_auth_headers(bob["access_token"]),
        json={"content": "dup", "client_message_id": "dup-1"},
    ).json()
    m2 = client.post(
        f"/api/v1/conversations/{conv['id']}/messages",
        headers=_auth_headers(bob["access_token"]),
        json={"content": "dup", "client_message_id": "dup-1"},
    ).json()
    assert m1["id"] == m2["id"]


def test_conversation_detail_forbidden_for_non_member(client, auth_headers):
    _register(client, "ken", "13700000108")
    _register(client, "lily", "13700000109")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "ken"},
    ).json()
    ken = _login(client, "ken")
    conv = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(ken["access_token"]),
    ).json()["conversation"]
    # lily（非成员）访问 → 403
    lily = _login(client, "lily")
    r = client.get(f"/api/v1/conversations/{conv['id']}", headers=_auth_headers(lily["access_token"]))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CONVERSATION_FORBIDDEN"


def test_message_pagination(client, auth_headers):
    _register(client, "mike", "13700000110")
    bob = auth_headers()
    req = client.post(
        "/api/v1/friends/requests",
        headers=_auth_headers(bob["access_token"]),
        json={"target_username_or_phone": "mike"},
    ).json()
    mike = _login(client, "mike")
    conv = client.post(
        f"/api/v1/friends/requests/{req['id']}/accept",
        headers=_auth_headers(mike["access_token"]),
    ).json()["conversation"]
    for i in range(5):
        client.post(
            f"/api/v1/conversations/{conv['id']}/messages",
            headers=_auth_headers(bob["access_token"]),
            json={"content": f"m{i}", "client_message_id": f"p{i}"},
        )
    # 第一页 limit=2
    p1 = client.get(
        f"/api/v1/conversations/{conv['id']}/messages?limit=2",
        headers=_auth_headers(bob["access_token"]),
    ).json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] != ""
    # 第二页
    p2 = client.get(
        f"/api/v1/conversations/{conv['id']}/messages?limit=2&cursor={p1['next_cursor']}",
        headers=_auth_headers(bob["access_token"]),
    ).json()
    assert len(p2["items"]) == 2
    # 不重叠
    assert p1["items"][-1]["id"] != p2["items"][0]["id"]


# ---------------- Device ----------------
def test_list_devices_contains_current(client, auth_headers):
    creds = auth_headers()
    r = client.get("/api/v1/devices", headers=_auth_headers(creds["access_token"]))
    assert r.status_code == 200
    assert any(d["id"] == creds["device_id"] for d in r.json())


def test_delete_device_revokes(client, auth_headers):
    creds = auth_headers()
    # 为同一用户再登一个桌面设备
    desk = _login(client, "bob", device_type="desktop")
    r = client.delete(
        f"/api/v1/devices/{desk['device']['id']}",
        headers=_auth_headers(creds["access_token"]),
    )
    assert r.status_code == 200 and r.json().get("ok") is True
    # 被移除设备的 refresh token 应失效 → 用其 refresh 拿新 access 应 401
    refresh = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": desk["refresh_token"]}
    )
    assert refresh.status_code == 401


def test_delete_device_other_user_forbidden(client, auth_headers):
    _register(client, "oscar", "13700000111")
    bob = auth_headers()
    oscar = _login(client, "oscar")
    r = client.delete(
        f"/api/v1/devices/{oscar['device']['id']}",
        headers=_auth_headers(bob["access_token"]),
    )
    assert r.status_code == 404  # 不同用户看不到该设备
