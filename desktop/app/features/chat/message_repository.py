"""Message repository — real API implementation (Desktop / PySide6, Phase 3E).

Wires the chat message flow to the existing ``ApiClient`` (requests) from
Phase 3A. NO second HTTP client. Endpoints follow API_CONTRACT §4:
  GET  /conversations/{id}/messages?cursor=&limit=
  POST /conversations/{id}/messages  { content, client_message_id }

Layering: UI → Controller → MessageRepository → ApiClient.
"""
from __future__ import annotations

from ...api.api_client import ApiClient
from .message_models import Message


class MessageRepository:
    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def get_messages(
        self, conversation_id: str, cursor: str = "", limit: int = 50
    ) -> list[Message]:
        params = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        resp = self._client.get(
            f"/conversations/{conversation_id}/messages", params=params
        )
        data = resp.json() or {}
        items = data.get("items") or []
        return [Message.from_json(m) for m in items]

    def send_message(
        self, conversation_id: str, content: str, client_message_id: str
    ) -> Message:
        resp = self._client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": content, "client_message_id": client_message_id},
        )
        return Message.from_json(resp.json())
