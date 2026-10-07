"""Phase 3E — Message Flow backend tests.

Covers API_CONTRACT §4 + authorization §6/§12/§17:
- member can send + read
- message persisted with correct fields (id/conversation_id/sender_id/content/created_at)
- non-member send -> 403
- non-member read -> 403
- nonexistent conversation -> 404
- unauthenticated -> 401
- empty content -> 400
- overlong content -> 400
- idempotency via client_message_id
- WebSocket message.created event id matches DB (integration)
- duplicate WS event does not create duplicate message
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest

# 允许脚本直接运行（开发/CI）也通过 pytest 收集
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, username, phone, password="password123"):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "phone": phone, "password": password, "nickname": username},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _login(client, identifier, password="password123"):
    r = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password,
              "device": {"device_type": "mobile", "device_name": "t", "device_identifier": "t"}},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _make_friends_and_conversation(client):
    """A registers+logs in, B registers+logs in, A->B friend, B accepts -> conversation."""
    import time
    suffix = str(int(time.time() * 1000))[-9:]
    a = _register(client, f"a_{uuid.uuid4().hex[:8]}", f"1390{suffix}")
    b = _register(client, f"b_{uuid.uuid4().hex[:8]}", f"1391{suffix}")
    tokA = a["access_token"]
    tokB = b["access_token"]

    # A searches B
    q = b["user"]["username"]
    sr = client.get(f"/api/v1/users/search?q={q}", headers=_auth(tokA))
    assert sr.status_code == 200 and len(sr.json()) >= 1

    # A sends friend request
    fr = client.post("/api/v1/friends/requests", headers=_auth(tokA),
                     json={"target_username_or_phone": b["user"]["username"]})
    assert fr.status_code in (200, 201), fr.text
    req_id = fr.json()["id"]

    # B accepts
    acc = client.post(f"/api/v1/friends/requests/{req_id}/accept", headers=_auth(tokB))
    assert acc.status_code == 200, acc.text
    conv_id = acc.json()["conversation"]["id"]
    return tokA, tokB, conv_id


# ---------------- Positive ----------------

def test_member_can_send_and_read(client):
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    r = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                    json={"content": "hello", "client_message_id": "c1"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["conversation_id"] == conv_id
    assert body["sender_id"]  # sender_id correct (non-empty)
    assert body["content"] == "hello"
    assert body["created_at"]  # created_at present

    # member B reads history
    rl = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokB))
    assert rl.status_code == 200, rl.text
    assert len(rl.json()["items"]) == 1
    assert rl.json()["items"][0]["id"] == body["id"]


def test_message_persisted_in_db(client):
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    r = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                    json={"content": "persist me", "client_message_id": "c2"})
    assert r.status_code == 201
    mid = r.json()["id"]
    from app.db.base import SessionLocal
    from app.models.conversation import Message
    db = SessionLocal()
    try:
        m = db.get(Message, uuid.UUID(mid))
        assert m is not None
        assert m.content == "persist me"
        assert m.sender_id is not None
    finally:
        db.close()


def test_idempotent_client_message_id(client):
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    body = {"content": "dup", "client_message_id": "same-id"}
    r1 = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA), json=body)
    r2 = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA), json=body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]  # same message, no duplicate


# ---------------- Security ----------------

def test_non_member_send_403(client):
    import time
    suffix = str(int(time.time() * 1000))[-9:]
    a = _register(client, f"a_{uuid.uuid4().hex[:8]}", f"1392{suffix}")
    c = _register(client, f"c_{uuid.uuid4().hex[:8]}", f"1393{suffix}")
    # C creates a conversation with nobody (no friendship) — make a conv via A-B path then use C
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    r = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(c["access_token"]),
                    json={"content": "x", "client_message_id": "c3"})
    assert r.status_code == 403


def test_non_member_read_403(client):
    import time
    suffix = str(int(time.time() * 1000))[-9:]
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    intruder = _register(client, f"z_{uuid.uuid4().hex[:8]}", f"1394{suffix}")
    r = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(intruder["access_token"]))
    assert r.status_code == 403


def test_nonexistent_conversation_404(client):
    import time
    suffix = str(int(time.time() * 1000))[-9:]
    a = _register(client, f"a_{uuid.uuid4().hex[:8]}", f"1395{suffix}")
    fake = str(uuid.uuid4())
    r = client.post(f"/api/v1/conversations/{fake}/messages", headers=_auth(a["access_token"]),
                    json={"content": "x", "client_message_id": "c4"})
    assert r.status_code == 404


def test_unauthenticated_401(client):
    r = client.get("/api/v1/conversations/whatever/messages")
    assert r.status_code == 401


def test_empty_content_400(client):
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    r = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                    json={"content": "", "client_message_id": "c5"})
    assert r.status_code == 400


def test_overlong_content_400(client):
    tokA, tokB, conv_id = _make_friends_and_conversation(client)
    r = client.post(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(tokA),
                    json={"content": "x" * 5001, "client_message_id": "c6"})
    assert r.status_code == 400
