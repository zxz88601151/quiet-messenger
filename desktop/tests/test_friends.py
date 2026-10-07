"""V1.1 Phase 3D Desktop friends/chat repository + controller tests.

Offscreen (QT_QPA_PLATFORM=offscreen) — no display needed.

Coverage:
- FriendRepository maps search/request/accept/reject/list/delete from real
  backend JSON (via a fake ApiClient, NOT a stub of business logic).
- FriendController orchestrates repo and exposes state (subscribe).
- ConversationRepository maps list/get.
- FriendsPage / ChatPage import + construct offscreen (UI ≠ API wiring smoke).

No message send is tested (Phase 3E).
"""
from __future__ import annotations

import os
import sys
import types

# Offscreen before importing PySide6.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock

import pytest


class _FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def json(self):
        return self._json

    @property
    def ok(self):
        return self.status_code < 400


class FakeApiClient:
    """Minimal fake of desktop ApiClient surface used by repositories.

    Records calls; returns canned backend JSON so repository mapping is
    genuinely exercised. Raises ApiException on a configured error.
    """

    def __init__(self, routes=None, error=None):
        # Normalize "METHOD /path" keys to "/path" for matching.
        raw = routes or {}
        self._routes = {
            (k.split(" ", 1)[1] if " " in k else k): v for k, v in raw.items()
        }
        self._error = error
        self.calls = []

    def _match(self, method, path):
        # routes maps path-prefix -> canned data. Match exact or by prefix.
        if path in self._routes:
            return self._routes[path]
        for p, val in self._routes.items():
            if path.startswith(p):
                return val
        raise AssertionError(f"No route for {method} {path}")

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        if self._error:
            raise self._error
        return _FakeResponse(self._match("GET", path))

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        if self._error:
            raise self._error
        return _FakeResponse(self._match("POST", path))

    def delete(self, path):
        self.calls.append(("DELETE", path, None))
        if self._error:
            raise self._error
        return _FakeResponse(self._match("DELETE", path))


def _make_repo(routes, error=None, current_user_id="me"):
    from app.features.friends.repository import FriendRepository
    from app.features.friends.models import FriendRequest, Friendship, UserSummary
    from app.storage.token_storage import TokenStorage
    from app.errors.api_exception import ApiException

    # Normalize "METHOD /path" keys to "/path" for FakeApiClient matching.
    norm = {k.split(" ", 1)[1] if " " in k else k: v for k, v in routes.items()}
    fake = FakeApiClient(norm, error=error)
    repo = FriendRepository(fake, TokenStorage(), current_user_id=current_user_id)
    return repo, fake


def test_search_users_maps_public_fields():
    routes = {
        "GET /users/search": [
            {"id": "u1", "username": "alice", "nickname": "Alice", "avatar": None}
        ]
    }
    repo, fake = _make_repo(routes)
    res = repo.search_users("alice")
    assert fake.calls[0][1] == "/users/search"
    assert res[0].username == "alice"
    assert res[0].nickname == "Alice"


def test_send_friend_request_posts_target():
    routes = {
        "POST /friends/requests": {
            "id": "r1", "sender_id": "me", "receiver_id": "bob", "status": "pending",
            "sender": {"id": "me", "username": "me", "nickname": "Me"},
            "receiver": {"id": "bob", "username": "bob", "nickname": "Bob"},
        }
    }
    repo, fake = _make_repo(routes)
    req = repo.send_friend_request("bob")
    assert req.id == "r1"
    assert req.is_incoming is False
    assert req.other_user.username == "bob"


def test_accept_returns_conversation_id():
    routes = {
        "POST /friends/requests/r1/accept": {
            "friendship": {"user": {"id": "bob", "username": "bob", "nickname": "Bob"},
                           "friendship_created_at": None},
            "conversation": {"id": "c001", "user_a": "a", "user_b": "b"},
        }
    }
    repo, fake = _make_repo(routes)
    result = repo.accept_friend_request("r1")
    assert result.conversation_id == "c001"
    assert result.friendship.user.username == "bob"


def test_reject_calls_reject_endpoint():
    routes = {"POST /friends/requests/r1/reject": {"ok": True}}
    repo, fake = _make_repo(routes)
    repo.reject_friend_request("r1")
    assert fake.calls[-1][0] == "POST"
    assert fake.calls[-1][1] == "/friends/requests/r1/reject"


def test_get_friends_maps_list():
    routes = {
        "GET /friends": [
            {"user": {"id": "bob", "username": "bob", "nickname": "Bob"},
             "friendship_created_at": None}
        ]
    }
    repo, _ = _make_repo(routes)
    friends = repo.get_friends()
    assert friends[0].user.username == "bob"


def test_delete_friend_calls_delete():
    routes = {"DELETE /friends/bob": {"ok": True}}
    repo, fake = _make_repo(routes)
    repo.delete_friend("bob")
    assert fake.calls[-1][1] == "/friends/bob"


def test_controller_accept_updates_state():
    from app.features.friends.state import FriendController
    from app.features.friends.repository import FriendRepository

    routes = {
        "POST /friends/requests/r1/accept": {
            "friendship": {"user": {"id": "bob", "username": "bob", "nickname": "Bob"},
                           "friendship_created_at": None},
            "conversation": {"id": "c001", "user_a": "a", "user_b": "b"},
        }
    }
    fake = FakeApiClient(routes)
    repo = FriendRepository(fake, MagicMock(), current_user_id="me")
    ctrl = FriendController(repo)
    ok = ctrl.accept("r1")
    assert ok is True
    assert ctrl.state.last_accepted_conversation_id == "c001"


def test_controller_maps_api_error():
    from app.features.friends.state import FriendController
    from app.features.friends.repository import FriendRepository
    from app.errors.api_exception import ApiException

    fake = FakeApiClient(error=ApiException("DUPLICATE_REQUEST", "已存在", 409))
    repo = FriendRepository(fake, MagicMock(), current_user_id="me")
    ctrl = FriendController(repo)
    ok = ctrl.send_request("bob")
    assert ok is False
    assert ctrl.state.error.code == "DUPLICATE_REQUEST"


def test_conversation_repository_maps_list():
    from app.features.chat.repository import ConversationRepository
    from app.features.chat.models import ConversationType

    routes = {
        "GET /conversations": [
            {"id": "c001", "user_a": "a", "user_b": "b",
             "peer": {"id": "bob", "username": "bob", "nickname": "Bob"},
             "last_message": {"content": "hi"}, "unread_count": 1}
        ]
    }
    fake = FakeApiClient(routes)
    repo = ConversationRepository(fake)
    convs = repo.get_conversations()
    assert convs[0].id == "c001"
    assert convs[0].peer.username == "bob"
    assert convs[0].type == ConversationType.DIRECT
    assert convs[0].last_message_preview == "hi"


def test_pages_construct_offscreen():
    """UI pages import + construct without a display (smoke for wiring)."""
    from PySide6.QtWidgets import QApplication

    from app.features.friends.state import FriendController
    from app.features.friends.repository import FriendRepository
    from app.features.chat.repository import ConversationRepository
    from app.features.friends.friends_page import FriendsPage
    from app.features.chat.chat_page import ChatPage

    app = QApplication.instance() or QApplication([])
    fake = FakeApiClient({})
    friend_repo = FriendRepository(fake, MagicMock(), current_user_id="me")
    friend_ctrl = FriendController(friend_repo)
    conv_repo = ConversationRepository(fake)

    page = FriendsPage(friend_ctrl)
    assert page is not None
    chat = ChatPage(conv_repo)
    assert chat is not None
    app.exit()
