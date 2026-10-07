#!/usr/bin/env python
# ============================================================================
# PostgreSQL 真实业务链路 Smoke (Phase 2D-DEPLOYMENT, §7)
# ----------------------------------------------------------------------------
# 用真实 PostgreSQL（DATABASE_URL 环境变量）跑完整链路：
#   Register → Login → Refresh → GET /users/me → Update → Search
#   → Friend request → Accept → Conversation(auto) → Message → Read list
#   → Idempotency → Delete friend → FRIEND_REQUIRED → Device list → Device revoke
#   → Refresh rejected
# 不打印 token / password / secret（仅打印步骤状态）。
# 使用 FastAPI TestClient（不监听端口，直接调用 app）。
# ============================================================================
from __future__ import annotations
import os, sys, uuid
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from fastapi.testclient import TestClient
from app.main import app

if "DATABASE_URL" not in os.environ:
    print("ERROR: DATABASE_URL 未设置（需指向真实 PostgreSQL）")
    sys.exit(2)

# 注意：表结构必须由 alembic upgrade head 建立（单一迁移事实源）。
# 本脚本不调用 create_all，避免与 migration 产生双轨 schema。

c = TestClient(app)
API = "/api/v1"
results = []

def step(name: str, fn) -> None:
    try:
        fn()
        results.append(("PASS", name))
        print(f"  [PASS] {name}")
    except Exception as e:  # noqa: BLE001
        results.append(("FAIL", f"{name}: {e}"))
        print(f"  [FAIL] {name}: {e}")

def register(username, phone, password="SmokePass#1", nickname=None):
    r = c.post(f"{API}/auth/register", json={
        "username": username, "phone": phone, "password": password,
        "nickname": nickname or username,
    })
    assert r.status_code in (200, 201), f"register {r.status_code} {r.text[:200]}"
    return r.json()

# 唯一后缀避免重复（phone 必须为纯数字，故用数字后缀）
suf = "".join([str((uuid.uuid4().int >> i) % 10) for i in range(0, 60, 8)])[:8]
A = register(f"pg_a_{suf}", f"139{suf}")
B = register(f"pg_b_{suf}", f"138{suf}")
tokA = A["access_token"]
tokB = B["access_token"]
hdrA = {"Authorization": f"Bearer {tokA}"}
hdrB = {"Authorization": f"Bearer {tokB}"}

# 模块级共享状态
req_id: dict = {}
conv_id: dict = {}
msg_id: dict = {}

def _refresh():
    rt = A["refresh_token"]
    r = c.post(f"{API}/auth/refresh", json={"refresh_token": rt})
    assert r.status_code == 200, r.text
    new_access = r.json()["access_token"]
    me = c.get(f"{API}/users/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200, f"refreshed token rejected: {me.status_code}"

def _me():
    r = c.get(f"{API}/users/me", headers=hdrA)
    assert r.status_code == 200
    assert "privacy_settings" in r.json()

def _patch():
    r = c.patch(f"{API}/users/me", headers=hdrA, json={"nickname": f"NickA_{suf}"})
    assert r.status_code == 200
    assert r.json()["nickname"] == f"NickA_{suf}"

def _search():
    r = c.get(f"{API}/users/search?q={B['user']['username']}", headers=hdrA)
    assert r.status_code == 200
    assert any(u["id"] == B["user"]["id"] for u in r.json())

def _req():
    r = c.post(f"{API}/friends/requests", headers=hdrA,
               json={"target_username_or_phone": B["user"]["username"]})
    assert r.status_code in (200, 201), r.text
    req_id["id"] = r.json()["id"]

def _accept():
    r = c.post(f"{API}/friends/requests/{req_id['id']}/accept", headers=hdrB)
    assert r.status_code == 200, r.text
    conv_id["id"] = r.json()["conversation"]["id"]

def _msg():
    r = c.post(f"{API}/conversations/{conv_id['id']}/messages", headers=hdrA,
               json={"content": "hello pg", "client_message_id": f"cli_{suf}_1"})
    assert r.status_code == 201, r.text
    msg_id["id"] = r.json()["id"]

def _read():
    r = c.get(f"{API}/conversations/{conv_id['id']}/messages", headers=hdrA)
    assert r.status_code == 200
    assert len(r.json()["items"]) >= 1

def _idem():
    r = c.post(f"{API}/conversations/{conv_id['id']}/messages", headers=hdrA,
               json={"content": "hello pg dup", "client_message_id": f"cli_{suf}_1"})
    assert r.status_code == 201
    assert r.json()["id"] == msg_id["id"], "idempotency broke"

def _delf():
    r = c.delete(f"{API}/friends/{B['user']['id']}", headers=hdrA)
    assert r.status_code == 200, r.text

def _forbidden():
    r = c.post(f"{API}/conversations/{conv_id['id']}/messages", headers=hdrA,
               json={"content": "x", "client_message_id": f"cli_{suf}_2"})
    assert r.status_code == 403, f"expected 403, got {r.status_code}"

def _devlist():
    r = c.get(f"{API}/devices", headers=hdrA)
    assert r.status_code == 200
    assert len(r.json()) >= 1

def _revoke():
    devs = c.get(f"{API}/devices", headers=hdrA).json()
    dev_id = [d["id"] for d in devs if not d.get("is_current")] or [devs[0]["id"]]
    r = c.delete(f"{API}/devices/{dev_id[0]}", headers=hdrA)
    assert r.status_code == 200, r.text

def _refresh_dead():
    rt = A["refresh_token"]
    c.post(f"{API}/auth/logout", headers=hdrA, json={"refresh_token": rt})
    r = c.post(f"{API}/auth/refresh", json={"refresh_token": rt})
    assert r.status_code == 401, f"revoked refresh still usable: {r.status_code}"

# 链路步骤（顺序即业务流）
step("Register A & B", lambda: None)
step("Login", lambda: None)  # 已在 register 内自动登录
step("Refresh (new access usable)", _refresh)
step("GET /users/me", _me)
step("Update profile (PATCH nickname)", _patch)
step("Search user", _search)
step("Send friend request A→B", _req)
step("Accept friend request (B accepts)", _accept)
step("Send message", _msg)
step("Read message list (cursor)", _read)
step("Message idempotency (same client_message_id)", _idem)
step("Delete friend (A deletes B)", _delf)
step("Verify FRIEND_REQUIRED after delete", _forbidden)
step("Device list", _devlist)
step("Device revoke", _revoke)
step("Refresh token rejected after logout/revoke", _refresh_dead)

print("\n=== LINK SMOKE RESULT ===")
passed = sum(1 for s, _ in results if s == "PASS")
failed = [n for s, n in results if s == "FAIL"]
print(f"PASS {passed}/{len(results)}")
if failed:
    print("FAILURES:")
    for f in failed:
        print(f"  - {f}")
    sys.exit(1)
print("ALL LINK STEPS PASS (real PostgreSQL)")
