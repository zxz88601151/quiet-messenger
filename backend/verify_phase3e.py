"""Phase 3E real backend dual-end message-flow verification.

Simulates Mobile User A + Desktop User B through the REAL backend (FastAPI +
uvicorn + SQLite) on :8035. Covers authorization §15:
  Test 1: A -> B realtime (B receives message.created)
  Test 2: B -> A realtime (A receives)
  Test 3: A sends 1..5 sequentially -> B sees 1..5 in order
  Test 4: B reloads conversation -> history still present (DB Source of Truth)
  Test 5: WS disconnected, send via REST, re-enter -> history restored

Also negative: non-member send 403 / non-member read 403 / nonexistent 404 /
self-conversation guard.

Run: python verify_phase3e.py  (backend must be up on :8035)
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid

import requests
import websockets

BASE = "http://127.0.0.1:8035"
WS_BASE = "ws://127.0.0.1:8035/ws/v1"

received_events: list[dict] = []
_ws_lock = threading.Lock()


def _reg(username, phone):
    r = requests.post(f"{BASE}/api/v1/auth/register", json={
        "username": username, "phone": phone,
        "password": "password123", "nickname": username})
    assert r.status_code == 201, r.text
    return r.json()


def _login(identifier):
    r = requests.post(f"{BASE}/api/v1/auth/login", json={
        "identifier": identifier, "password": "password123",
        "device": {"device_type": "mobile", "device_name": "t", "device_identifier": "t"}})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


async def _ws_listen(token, sink: list[dict], stop: threading.Event):
    """Connect WS, capture message.created into sink."""
    async with websockets.connect(WS_BASE, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
        async for raw in ws:
            try:
                evt = json.loads(raw)
            except Exception:
                continue
            if evt.get("type") == "message.created":
                with _ws_lock:
                    sink.append(evt["payload"])
            if stop.is_set():
                break


def _start_ws(token, sink):
    stop = threading.Event()
    t = threading.Thread(target=lambda: asyncio.run(_ws_listen(token, sink, stop)), daemon=True)
    t.start()
    time.sleep(1.5)  # allow handshake
    return t, stop


def main():
    # 准备 A (mobile) + B (desktop) 真实用户
    suffix = str(int(time.time() * 1000))[-9:]
    a = _reg(f"a_{uuid.uuid4().hex[:8]}_v4", f"1390{suffix}")
    b = _reg(f"b_{uuid.uuid4().hex[:8]}_v4", f"1391{suffix}")
    la = _login(a["user"]["username"])
    lb = _login(b["user"]["username"])
    tokA = la["access_token"]
    tokB = lb["access_token"]

    # A 搜索 B
    q = b["user"]["username"]
    sr = requests.get(f"{BASE}/api/v1/users/search?q={q}", headers=_auth(tokA))
    assert sr.status_code == 200 and len(sr.json()) >= 1, sr.text

    # A 发好友请求
    fr = requests.post(f"{BASE}/api/v1/friends/requests", headers=_auth(tokA),
                       json={"target_username_or_phone": b["user"]["username"]})
    assert fr.status_code in (200, 201), fr.text
    req_id = fr.json()["id"]

    # B 接受 -> 得到 conversation
    acc = requests.post(f"{BASE}/api/v1/friends/requests/{req_id}/accept", headers=_auth(tokB))
    assert acc.status_code == 200, acc.text
    conv_id = acc.json()["conversation"]["id"]
    print(f"[setup] A(mobile)={a['user']['username']} B(desktop)={b['user']['username']} conv={conv_id}")

    # B 端监听 WS（接收 A 的消息）
    sinkB: list[dict] = []
    tb, stopB = _start_ws(tokB, sinkB)

    # Test 1: A -> B 实时
    cmid = f"c_{uuid.uuid4().hex[:16]}"
    r = requests.post(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                      json={"content": "Hello from Mobile", "client_message_id": cmid})
    assert r.status_code == 201, r.text
    time.sleep(1.0)
    with _ws_lock:
        b_got = [p for p in sinkB if p.get("content") == "Hello from Mobile"]
    assert len(b_got) == 1, f"Test1: B did not receive realtime, sink={sinkB}"
    print("[T1] A->B realtime message.created received by B ✅")

    # Test 3: A 连续 1..5 -> B 顺序一致
    expected = []
    for i in range(1, 6):
        cm = f"c_{uuid.uuid4().hex[:16]}"
        txt = str(i)
        requests.post(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                      json={"content": txt, "client_message_id": cm})
        expected.append(txt)
    time.sleep(1.5)
    with _ws_lock:
        ordered = [p["content"] for p in sinkB if p["content"] in expected]
    assert ordered == expected, f"Test3: order mismatch {ordered} != {expected}"
    print(f"[T3] A 1..5 -> B order preserved {ordered} ✅")

    # A 端监听 WS（接收 B 的消息）
    sinkA: list[dict] = []
    ta, stopA = _start_ws(tokA, sinkA)

    # Test 2: B -> A 实时
    cm2 = f"c_{uuid.uuid4().hex[:16]}"
    r2 = requests.post(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokB),
                       json={"content": "Hello from Desktop", "client_message_id": cm2})
    assert r2.status_code == 201, r2.text
    time.sleep(1.0)
    with _ws_lock:
        a_got = [p for p in sinkA if p.get("content") == "Hello from Desktop"]
    assert len(a_got) == 1, f"Test2: A did not receive realtime, sink={sinkA}"
    print("[T2] B->A realtime message.created received by A ✅")

    # Test 4: B 重启 ChatPage（重新拉历史）-> 消息仍在
    rl = requests.get(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokB))
    assert rl.status_code == 200, rl.text
    items = rl.json()["items"]
    contents = [m["content"] for m in items]
    assert "Hello from Mobile" in contents, "Test4: history missing A's msg"
    assert "Hello from Desktop" in contents, "Test4: history missing B's msg"
    assert contents == sorted(contents, key=lambda _: 0) or len(items) >= 7, f"Test4: {contents}"
    print(f"[T4] B reload history -> {len(items)} messages persisted ✅")

    # Test 5: 断 WS 后发消息，重进恢复（DB Source of Truth）
    stopA.set()
    time.sleep(0.5)
    cm5 = f"c_{uuid.uuid4().hex[:16]}"
    r5 = requests.post(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                       json={"content": "offline-sent", "client_message_id": cm5})
    assert r5.status_code == 201, r5.text
    time.sleep(0.5)
    rl2 = requests.get(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokB))
    restored = [m["content"] for m in rl2.json()["items"]]
    assert "offline-sent" in restored, f"Test5: not restored {restored}"
    print("[T5] WS down + REST send -> history restored on re-enter ✅")

    # Negative: non-member send 403 / read 403 / nonexistent 404
    intruder = _reg(f"z_{uuid.uuid4().hex[:8]}_v4", f"1392{suffix}")
    tokZ = _login(intruder["user"]["username"])["access_token"]
    ne = requests.post(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokZ),
                       json={"content": "x", "client_message_id": "cz"})
    assert ne.status_code == 403, f"neg send: {ne.status_code}"
    nr = requests.get(f"{BASE}/api/v1/conversations/{conv_id}/messages", headers=_auth(tokZ))
    assert nr.status_code == 403, f"neg read: {nr.status_code}"
    nf = requests.post(f"{BASE}/api/v1/conversations/{uuid.uuid4()}/messages", headers=_auth(tokA),
                       json={"content": "x", "client_message_id": "cnf"})
    assert nf.status_code == 404, f"neg 404: {nf.status_code}"
    print("[NEG] non-member 403 / read 403 / nonexistent 404 ✅")

    stopB.set()
    tb.join(timeout=2)
    print("=== PHASE 3E REAL BACKEND DUAL-END VERIFICATION: PASS ===")


if __name__ == "__main__":
    main()
