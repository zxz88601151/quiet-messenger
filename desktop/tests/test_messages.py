"""Phase 3E — Desktop message flow tests (offscreen).

Covers MessageController (history load, send optimistic+confirm, WS dedup)
and MessageRepository (request shape + parse) with a fake ApiClient. No real
backend, no fabricated PASS.

Run: QT_QPA_PLATFORM=offscreen python -m pytest tests/test_messages.py
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.api.api_client import ApiClient
from app.errors.api_exception import ApiException
from app.features.auth.state import AuthController
from app.features.chat.message_models import Message, MessageUiState
from app.features.chat.message_repository import MessageRepository
from app.features.chat.message_state import MessageController
from app.realtime.event_envelope import EventEnvelope
from app.realtime.realtime_client import RealtimeClient


class FakeResponse:
    def __init__(self, data: Any, status: int = 200) -> None:
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


class FakeApiClient(ApiClient):
    """In-memory ApiClient stub. `routes` maps path -> list|dict. `error`=ApiException to raise."""

    def __init__(self, routes=None, error=None) -> None:
        # Skip real ApiClient.__init__ (needs token storage + requests session).
        self._routes = routes or {}
        self._error = error
        self.calls: list[tuple[str, str, Any]] = []

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if self._error:
            raise self._error
        return FakeResponse(self._routes.get(path, {"items": [], "next_cursor": ""}))

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        if self._error:
            raise self._error
        return FakeResponse(self._routes.get(path, {"id": str(uuid.uuid4()), "conversation_id": "c1",
                                                      "sender_id": "u1", "content": json.get("content") if json else "",
                                                      "created_at": "2026-08-24T00:00:00+00:00"}), 201)


class FakeRealtime:
    """Captures event listeners; lets tests inject WS events."""

    def __init__(self) -> None:
        self.on_event = None  # legacy single callback
        self._listeners: list = []

    def add_event_listener(self, cb):
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb) if cb in self._listeners else None

    def remove_event_listener(self, cb):
        if cb in self._listeners:
            self._listeners.remove(cb)

    def add_state_listener(self, cb):
        """State listener stub for offline message catch-up (DEF-RT-010 parity)."""
        return lambda: None

    def inject(self, evt: EventEnvelope) -> None:
        if self.on_event:
            self.on_event(evt)
        for cb in list(self._listeners):
            cb(evt)


@pytest.fixture
def fake_realtime():
    return FakeRealtime()


def _make_controller(fake, realtime, conv_id="c1", current="u1"):
    repo = MessageRepository(fake)
    ctrl = MessageController(repo, realtime, current, conv_id)  # type: ignore[arg-type]
    return ctrl


def test_load_history_maps_items():
    fake = FakeApiClient({
        "/conversations/c1/messages": {
            "items": [
                {"id": "m1", "conversation_id": "c1", "sender_id": "u2", "content": "hi",
                 "created_at": "2026-08-24T00:00:00+00:00"},
                {"id": "m2", "conversation_id": "c1", "sender_id": "u1", "content": "yo",
                 "created_at": "2026-08-24T00:00:01+00:00"},
            ],
            "next_cursor": "",
        }
    })
    realtime = FakeRealtime()
    ctrl = _make_controller(fake, realtime)
    ctrl.load()
    assert len(ctrl.messages) == 2
    assert ctrl.messages[0].id == "m1"
    assert ctrl.messages[1].content == "yo"
    assert ctrl.loading is False


def test_send_optimistic_then_confirmed():
    msg_id = str(uuid.uuid4())
    fake = FakeApiClient({
        "/conversations/c1/messages": {
            "id": msg_id, "conversation_id": "c1", "sender_id": "u1", "content": "hello",
            "client_message_id": "c_local", "created_at": "2026-08-24T00:00:00+00:00",
        }
    })
    realtime = FakeRealtime()
    ctrl = _make_controller(fake, realtime)
    ctrl.send("hello")
    # optimistic first (mine), then replaced by confirmed (sent)
    assert any(m.content == "hello" for m in ctrl.messages)
    confirmed = [m for m in ctrl.messages if m.id == msg_id]
    assert len(confirmed) == 1
    assert confirmed[0].ui_state == MessageUiState.SENT


def test_ws_message_created_dedup():
    fake = FakeApiClient({
        "/conversations/c1/messages": {"items": [
            {"id": "m1", "conversation_id": "c1", "sender_id": "u2", "content": "from peer",
             "created_at": "2026-08-24T00:00:00+00:00"}], "next_cursor": ""}
    })
    realtime = FakeRealtime()
    ctrl = _make_controller(fake, realtime)
    ctrl.load()
    # Peer sends via WS
    realtime.inject(EventEnvelope(
        type="message.created",
        payload={"id": "m2", "conversation_id": "c1", "sender_id": "u2", "content": "ws hi",
                 "created_at": "2026-08-24T00:00:02+00:00"},
    ))
    assert len(ctrl.messages) == 2
    assert ctrl.messages[-1].content == "ws hi"
    # Duplicate WS event (same id) must NOT add a second message.
    realtime.inject(EventEnvelope(
        type="message.created",
        payload={"id": "m2", "conversation_id": "c1", "sender_id": "u2", "content": "ws hi",
                 "created_at": "2026-08-24T00:00:02+00:00"},
    ))
    assert len(ctrl.messages) == 2


def test_ws_event_other_conversation_ignored():
    fake = FakeApiClient()
    realtime = FakeRealtime()
    ctrl = _make_controller(fake, realtime, conv_id="c1")
    realtime.inject(EventEnvelope(
        type="message.created",
        payload={"id": "mx", "conversation_id": "other", "sender_id": "u2", "content": "x"},
    ))
    assert ctrl.messages == []


def test_send_error_marks_failed():
    fake = FakeApiClient(error=ApiException("SEND_FAIL", "发送失败", 400))
    realtime = FakeRealtime()
    ctrl = _make_controller(fake, realtime)
    ctrl.send("boom")
    failed = [m for m in ctrl.messages if m.ui_state == MessageUiState.FAILED]
    assert len(failed) == 1
    assert ctrl.error is not None


def test_repository_request_shape():
    fake = FakeApiClient()
    repo = MessageRepository(fake)
    repo.send_message("c1", "hi", "c_local")
    assert fake.calls[-1][0] == "POST"
    assert fake.calls[-1][1] == "/conversations/c1/messages"
    assert fake.calls[-1][2]["content"] == "hi"
    assert fake.calls[-1][2]["client_message_id"] == "c_local"


def test_is_own_message_attribution():
    """Phase 3F — ownership attribution regression (Desktop).

    The ONLY correct rule is sender_id == current_user_id. client_message_id
    is an idempotency key returned for BOTH peers and must NOT be used.
    """
    from app.features.chat.message_models import is_own_message

    mine = Message(id="m1", conversation_id="c1", sender_id="u1",
                   content="hi", client_message_id="c-u1")
    peer = Message(id="m2", conversation_id="c1", sender_id="u2",
                   content="hey", client_message_id="c-u2")

    assert is_own_message(mine, "u1") is True
    assert is_own_message(peer, "u1") is False


def test_is_own_message_regression_client_id_ignored():
    """Critical anti-regression: peer's message with client_message_id set must
    NOT be attributed as mine."""
    from app.features.chat.message_models import is_own_message

    peer = Message(id="m3", conversation_id="c1", sender_id="u2",
                   content="x", client_message_id="c-u2")
    assert peer.client_message_id is not None  # precondition
    # OLD buggy predicate `client_message_id is not None` -> True (wrong).
    assert is_own_message(peer, "u1") is False  # correct: still peer


def test_pages_construct_offscreen():
    """Smoke: ChatPage imports + constructs with real repos (no display)."""
    from PySide6.QtWidgets import QApplication
    from app.features.chat.chat_page import ChatPage
    from app.features.chat.repository import ConversationRepository
    from app.features.chat.message_repository import MessageRepository
    from app.api.api_client import ApiClient
    from app.storage.token_storage import TokenStorage

    app = QApplication.instance() or QApplication([])
    fake = FakeApiClient()
    api = ApiClient(token_storage=TokenStorage())
    conv_repo = ConversationRepository(api)
    msg_repo = MessageRepository(api)
    realtime = RealtimeClient(
        base_url="http://127.0.0.1:8000",
        get_token=lambda: None,
        on_token_expired=lambda: __import__("asyncio").coroutine(lambda: False)(),  # type: ignore
        on_event=lambda _e: None,
    )
    page = ChatPage(conv_repo, msg_repo, realtime, current_user_id="u1")
    assert page is not None
