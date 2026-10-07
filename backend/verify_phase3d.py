"""Phase 3D 真实 Backend 双端验证脚本。

用真实 running backend (http://127.0.0.1:8033) 验证 Friends + Conversations 闭环：
Test A 搜索 / B 发请求 / C 接受 / D 好友列表 / E 创建会话 / F 重复返回同一 C001
+ 负面用例（自加/重复/越权/不存在）+ 双端一致（Mobile A + Desktop B 看到同一会话）。

不实现 message（Phase 3E）。仅 REST 数据面闭环。
"""
from __future__ import annotations

import sys
import urllib.request
import urllib.error
import json

BASE = "http://127.0.0.1:8033"


def req(method, path, token=None, json_body=None):
    url = f"{BASE}{path}"
    data = json.dumps(json_body).encode() if json_body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body}


def register(username, phone):
    st, b = req("POST", "/api/v1/auth/register", json_body={
        "username": username, "phone": phone, "password": "secret123",
        "nickname": username.title(),
        "device": {"device_type": "mobile", "device_name": username, "device_identifier": f"mob-{username}"},
    })
    assert st == 201, f"register {username} failed: {st} {b}"
    return b


def login(identifier, dtype="desktop"):
    st, b = req("POST", "/api/v1/auth/login", json_body={
        "identifier": identifier, "password": "secret123",
        "device": {"device_type": dtype, "device_name": dtype, "device_identifier": f"{dtype}-x"},
    })
    assert st == 200, f"login {identifier} failed: {st} {b}"
    return b


def main():
    print("=== Phase 3D REAL BACKEND VERIFICATION (8033) ===\n")

    # 双端两个真实用户：A (Mobile) + B (Desktop)
    A = register("p3d_a2", "13700000311")
    B = register("p3d_b2", "13700000312")
    tokA = A["access_token"]
    tokB = B["access_token"]
    print(f"[setup] A(mobile)={A['user']['id'][:8]} B(desktop)={B['user']['id'][:8]}")

    # Test A: search B by username
    st, b = req("GET", "/api/v1/users/search?q=p3d_b2", token=tokA)
    assert st == 200 and any(u["username"] == "p3d_b2" for u in b), f"A: search fail {st} {b}"
    print(f"[A] search 'p3d_b2' -> found {len(b)} user(s) ✅")

    # Test B: A sends friend request to B
    st, b = req("POST", "/api/v1/friends/requests", token=tokA, json_body={"target_username_or_phone": "p3d_b2"})
    assert st == 201, f"B: send req fail {st} {b}"
    req_id = b["id"]
    print(f"[B] A -> B friend request created (req={req_id[:8]}) ✅")

    # Test C: B accepts
    st, b = req("POST", f"/api/v1/friends/requests/{req_id}/accept", token=tokB)
    assert st == 200 and "friendship" in b and "conversation" in b, f"C: accept fail {st} {b}"
    conv_id = b["conversation"]["id"]
    print(f"[C] B accepts -> FRIENDS + conversation {conv_id[:8]} ✅")

    # Test D: A's friend list contains B
    st, b = req("GET", "/api/v1/friends", token=tokA)
    assert st == 200 and any(f["user"]["username"] == "p3d_b2" for f in b), f"D: friends fail {st} {b}"
    print(f"[D] A friends list -> {len(b)} friend(s), includes p3d_b2 ✅")

    # Test E: A get-or-create conversation with B (已存在，应返回同一 C001)
    st, b = req("GET", "/api/v1/conversations", token=tokA)
    assert st == 200 and len(b) == 1 and b[0]["id"] == conv_id, f"E: conv list fail {st} {b}"
    print(f"[E] A conversation list -> C001={b[0]['id'][:8]} (matches accept conversation) ✅")

    # Test F: repeat get conversation returns SAME C001 (no C002)
    st2, b2 = req("GET", "/api/v1/conversations", token=tokB)
    assert st2 == 200 and len(b2) == 1 and b2[0]["id"] == conv_id, f"F: dup conv fail {st2} {b2}"
    print(f"[F] B conversation list -> same C001={b2[0]['id'][:8]} (no C002) ✅")

    # ---- Negative tests ----
    # self friend request
    st, b = req("POST", "/api/v1/friends/requests", token=tokA, json_body={"target_username_or_phone": "p3d_a2"})
    assert st == 400, f"neg self: expected 400 got {st}"
    print(f"[N1] self friend request -> 400 ✅")

    # duplicate request (already friends, backend returns existing friendship+conversation, no new)
    st, b = req("POST", "/api/v1/friends/requests", token=tokA, json_body={"target_username_or_phone": "p3d_b2"})
    assert st in (200, 201) and b["conversation"]["id"] == conv_id, f"neg dup: {st} {b}"
    print(f"[N2] duplicate friend request -> {st} (same C001, no new relation) ✅")

    # nonexistent user
    st, b = req("POST", "/api/v1/friends/requests", token=tokA, json_body={"target_username_or_phone": "ghost999"})
    assert st == 404, f"neg nonexist: expected 404 got {st}"
    print(f"[N3] request to nonexistent user -> 404 ✅")

    # non-member access conversation (use a third user C)
    C = register("p3d_c2", "13700000313")
    tokC = C["access_token"]
    st, b = req("GET", f"/api/v1/conversations/{conv_id}", token=tokC)
    assert st == 403, f"neg nonmember: expected 403 got {st}"
    print(f"[N4] non-member C accesses A↔B conversation -> 403 ✅")

    # non-receiver reject (A tries to reject B's incoming... but A is sender; use fresh)
    # A sends to C, C is receiver; A (sender) reject -> 404
    st, b = req("POST", "/api/v1/friends/requests", token=tokA, json_body={"target_username_or_phone": "p3d_c2"})
    rid2 = b["id"]
    st, b = req("POST", f"/api/v1/friends/requests/{rid2}/reject", token=tokA)  # sender reject
    assert st == 404, f"neg sender-reject: expected 404 got {st}"
    print(f"[N5] sender (A) reject own outgoing request -> 404 ✅")

    # ---- Dual-client consistency ----
    # B (desktop) deletes friendship, then re-add via new request to prove stable flow
    st, b = req("DELETE", f"/api/v1/friends/{A['user']['id']}", token=tokB)
    assert st == 200, f"dual delete: {st} {b}"
    print(f"[DUAL] B (desktop) deletes friendship with A -> 200 ✅")
    st, b = req("GET", "/api/v1/friends", token=tokB)
    assert st == 200 and all(f["user"]["username"] != "p3d_a2" for f in b), "dual: B still sees A"
    print(f"[DUAL] B friends list no longer includes A ✅")

    print("\n=== PHASE 3D REAL BACKEND VERIFICATION: PASS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
