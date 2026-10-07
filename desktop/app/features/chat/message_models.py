"""Message domain model (Desktop / PySide6, Phase 3E).

Minimal DIRECT message. Matches backend `MessagePublic` (API_CONTRACT §4).
Fields: id / conversation_id / sender_id / content / created_at.
No status/typing/read-receipt/edit/recall — out of scope (Phase 3E §3).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class MessageUiState(str, Enum):
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


@dataclass
class Message:
    id: str
    conversation_id: str
    sender_id: str
    content: str
    client_message_id: Optional[str] = None
    created_at: Optional[datetime] = None
    ui_state: MessageUiState = MessageUiState.SENT

    @classmethod
    def from_json(cls, d: dict) -> "Message":
        created = d.get("created_at")
        if isinstance(created, str):
            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
        return cls(
            id=str(d["id"]),
            conversation_id=str(d["conversation_id"]),
            sender_id=str(d["sender_id"]),
            content=d["content"],
            client_message_id=d.get("client_message_id"),
            created_at=created,
            ui_state=MessageUiState.SENT,
        )

    @classmethod
    def optimistic(
        cls, conversation_id: str, sender_id: str, content: str, client_message_id: str
    ) -> "Message":
        return cls(
            id=client_message_id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            content=content,
            client_message_id=client_message_id,
            created_at=datetime.now(),
            ui_state=MessageUiState.SENDING,
        )

    def copy_with(self, ui_state: MessageUiState, id: Optional[str] = None) -> "Message":
        return Message(
            id=id or self.id,
            conversation_id=self.conversation_id,
            sender_id=self.sender_id,
            content=self.content,
            client_message_id=self.client_message_id,
            created_at=self.created_at,
            ui_state=ui_state,
        )


def is_own_message(message: "Message", current_user_id: str) -> bool:
    """Ownership attribution — the ONLY correct rule is sender_id == current_user_id.

    `client_message_id` is an idempotency key returned by the backend for BOTH
    peers; it is NOT an ownership marker. The prior `Message.is_mine` property
    relied on `client_message_id is not None` and therefore rendered every
    received message as "mine" (Phase 3F fix).
    """
    return message.sender_id == current_user_id
