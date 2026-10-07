"""Friend repository — real API implementation (Desktop / PySide6, Phase 3D).

Wires the friends feature to the existing ``ApiClient`` (requests) + TokenStorage
from Phase 3A. NO second HTTP client. Endpoints follow API_CONTRACT §2/§3.

Scope (Phase 3D only): search / request / accept / reject / list / delete.
No message / conversation-send / websocket / QR / group logic.

Layering: UI → Controller → FriendRepository → ApiClient → Backend.
"""
from __future__ import annotations

from ...api.api_client import ApiClient
from ...storage.token_storage import TokenStorage
from ...errors.api_exception import ApiException
from .models import AcceptResult, FriendRequest, Friendship, UserSummary


class FriendRepository:
    def __init__(self, client: ApiClient, token_storage: TokenStorage, current_user_id: str = "") -> None:
        self._client = client
        self._tokens = token_storage
        self._current_user_id = current_user_id

    def search_users(self, query: str) -> list[UserSummary]:
        resp = self._client.get("/users/search", params={"q": query, "limit": 20})
        return [UserSummary.from_json(u) for u in (resp.json() or [])]

    def send_friend_request(self, target: str) -> FriendRequest:
        resp = self._client.post(
            "/friends/requests", json={"target_username_or_phone": target}
        )
        return FriendRequest.from_json(resp.json(), self._current_user_id)

    def get_requests(self, req_type: str = "all") -> list[FriendRequest]:
        resp = self._client.get("/friends/requests", params={"type": req_type})
        return [FriendRequest.from_json(r, self._current_user_id) for r in (resp.json() or [])]

    def accept_friend_request(self, request_id: str) -> AcceptResult:
        resp = self._client.post(f"/friends/requests/{request_id}/accept")
        d = resp.json()
        conv = d["conversation"]
        return AcceptResult(
            friendship=Friendship.from_json(d["friendship"]),
            conversation_id=str(conv["id"]),
        )

    def reject_friend_request(self, request_id: str) -> None:
        self._client.post(f"/friends/requests/{request_id}/reject")

    def get_friends(self) -> list[Friendship]:
        resp = self._client.get("/friends")
        return [Friendship.from_json(f) for f in (resp.json() or [])]

    def delete_friend(self, friend_id: str) -> None:
        self._client.delete(f"/friends/{friend_id}")
