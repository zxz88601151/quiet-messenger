"""V1.1 Phase 3D 补充社交测试 — 覆盖授权§29 要求的 Phase 2C test_social 缺漏项。

重点：
- 重复 accept（已 accepted 再 accept → 409 CONFLICT）
- 非 receiver 拒绝（sender 调 reject → 404）
- conversation 不存在 → 404
- conversation 唯一性（重复 accept 返回同一 C001，不产生 C002）
- 自加自己 / 重复请求 / 非成员越权（已在 test_social 覆盖，这里只做 Phase 3D 收口断言）

范围：不测试 WS 推送（Phase 5）/ QR（Phase 6）/ message 流（Phase 3E 的发送逻辑不在此）。
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_request(client, sender_tok, target):
    r = client.post(
        "/api/v1/friends/requests",
        headers=_auth(sender_tok),
        json={"target_username_or_phone": target},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------- Uniqueness ----------------
def test_conversation_created_once_not_duplicated(client, auth_headers):
    """Phase 3D §14/§15/§25-F：重复 accept 必须返回同一 C001，不产生 C002。"""
    _register(client, "uniq_a", "13700000201")
    _register(client, "uniq_b", "13700000202")
    bob = auth_headers()
    req_id = _make_request(client, bob["access_token"], "uniq_b")
    uni_b = _login(client, "uniq_b")

    c1 = client.post(
        f"/api/v1/friends/requests/{req_id}/accept",
        headers=_auth(uni_b["access_token"]),
    ).json()["conversation"]["id"]

    # 再次尝试发请求（已是好友，返回既有友谊 + 同一 conversation）
    dup = client.post(
        "/api/v1/friends/requests",
        headers=_auth(bob["access_token"]),
        json={"target_username_or_phone": "uniq_b"},
    ).json()
    assert "conversation" in dup
    assert dup["conversation"]["id"] == c1, "重复加好友必须返回同一会话 C001"

    # 双方 conversation list 各且仅有一个 direct conversation
    cl_bob = client.get("/api/v1/conversations", headers=_auth(bob["access_token"])).json()
    cl_uni = client.get("/api/v1/conversations", headers=_auth(uni_b["access_token"])).json()
    assert len(cl_bob) == 1 and cl_bob[0]["id"] == c1
    assert len(cl_uni) == 1 and cl_uni[0]["id"] == c1


# ---------------- Accept idempotency ----------------
def test_accept_already_accepted_conflicts(client, auth_headers):
    """重复 accept（已 accepted）→ 409 CONFLICT（不重复建 Friendship/Conversation）。"""
    _register(client, "acc_a", "13700000203")
    _register(client, "acc_b", "13700000204")
    bob = auth_headers()
    req_id = _make_request(client, bob["access_token"], "acc_b")
    acc_b = _login(client, "acc_b")
    first = client.post(
        f"/api/v1/friends/requests/{req_id}/accept",
        headers=_auth(acc_b["access_token"]),
    )
    assert first.status_code == 200
    second = client.post(
        f"/api/v1/friends/requests/{req_id}/accept",
        headers=_auth(acc_b["access_token"]),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


# ---------------- Reject authorization ----------------
def test_reject_requires_receiver(client, auth_headers):
    """非 receiver（sender）调 reject → 404（仅接收方可操作）。"""
    _register(client, "rej_a", "13700000205")
    _register(client, "rej_b", "13700000206")
    bob = auth_headers()
    req_id = _make_request(client, bob["access_token"], "rej_b")
    # bob（sender）尝试 reject → 404
    rj = client.post(
        f"/api/v1/friends/requests/{req_id}/reject",
        headers=_auth(bob["access_token"]),
    )
    assert rj.status_code == 404


def test_reject_then_accept_conflicts(client, auth_headers):
    """已 rejected 后再 accept → 409（终态不可逆）。"""
    _register(client, "rja", "13700000207")
    _register(client, "rjb", "13700000208")
    bob = auth_headers()
    req_id = _make_request(client, bob["access_token"], "rjb")
    rjb = _login(client, "rjb")
    rej = client.post(
        f"/api/v1/friends/requests/{req_id}/reject",
        headers=_auth(rjb["access_token"]),
    )
    assert rej.status_code == 200
    acc = client.post(
        f"/api/v1/friends/requests/{req_id}/accept",
        headers=_auth(rjb["access_token"]),
    )
    assert acc.status_code == 409


# ---------------- Conversation not found ----------------
def test_get_conversation_not_found(client, auth_headers):
    """不存在的 conversation id → 404 NOT_FOUND。"""
    bob = auth_headers()
    import uuid
    fake = str(uuid.uuid4())
    r = client.get(f"/api/v1/conversations/{fake}", headers=_auth(bob["access_token"]))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_get_conversation_bad_uuid(client, auth_headers):
    """非法 UUID → 404（统一 NOT_FOUND，不暴露内部格式）。"""
    bob = auth_headers()
    r = client.get("/api/v1/conversations/not-a-uuid", headers=_auth(bob["access_token"]))
    assert r.status_code == 404


# ---------------- Negative: self / duplicate / nonexistent ----------------
def test_self_friend_request_rejected(client, auth_headers):
    """自己加自己 → 400（不建立 A→A）。"""
    bob = auth_headers(username="selfuser", phone="13700000210")
    r = client.post(
        "/api/v1/friends/requests",
        headers=_auth(bob["access_token"]),
        json={"target_username_or_phone": "selfuser"},
    )
    assert r.status_code == 400


def test_duplicate_friend_request_conflicts(client, auth_headers):
    """重复发送好友请求 → 409 DUPLICATE_REQUEST。"""
    _register(client, "dup_a", "13700000209")
    bob = auth_headers()
    p = {"target_username_or_phone": "dup_a"}
    r1 = client.post("/api/v1/friends/requests", headers=_auth(bob["access_token"]), json=p)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/friends/requests", headers=_auth(bob["access_token"]), json=p)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DUPLICATE_REQUEST"


def test_friend_request_nonexistent_user(client, auth_headers):
    """不存在的用户 → 404 NOT_FOUND。"""
    bob = auth_headers()
    r = client.post(
        "/api/v1/friends/requests",
        headers=_auth(bob["access_token"]),
        json={"target_username_or_phone": "no_such_user_999"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_delete_nonexistent_friend(client, auth_headers):
    """删除不存在的好友 → 404 FRIEND_NOT_FOUND。"""
    bob = auth_headers()
    import uuid
    r = client.delete(
        f"/api/v1/friends/{uuid.uuid4()}",
        headers=_auth(bob["access_token"]),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "FRIEND_NOT_FOUND"
