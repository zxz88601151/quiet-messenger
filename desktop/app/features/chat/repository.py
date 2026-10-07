"""Conversation repository — real API implementation (Desktop / PySide6, Phase 3D).

Wires the chat feature to the existing ``ApiClient`` (requests) from Phase 3A.
NO second HTTP client. Endpoints follow API_CONTRACT §4.

Scope (Phase 3D only): list conversations + get a single conversation. The
"Get/Create Direct Conversation" step is fulfilled by the backend at friend-
accept time (API_CONTRACT §3 returns {friendship, conversation}), so the client
only needs read access here. Message send/list belongs to Phase 3E — this
repository deliberately exposes NO send() method.

Layering: UI → Controller → ConversationRepository → ApiClient.
"""
from __future__ import annotations

from ...api.api_client import ApiClient
from ...errors.api_exception import ApiException
from .models import Conversation


class ConversationRepository:
    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def get_conversations(self) -> list[Conversation]:
        resp = self._client.get("/conversations")
        return [Conversation.from_json(c) for c in (resp.json() or [])]

    def get_conversation(self, conversation_id: str) -> Conversation:
        resp = self._client.get(f"/conversations/{conversation_id}")
        return Conversation.from_json(resp.json())
