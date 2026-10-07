"""Conversation domain model (Desktop / PySide6, Phase 3D).

Backend `ConversationPublic` (API_CONTRACT §4). V1.1 implements only the
DIRECT (one-to-one) type — no GROUP / CHANNEL / COMMUNITY / BROADCAST.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from ..friends.models import UserSummary


class ConversationType(str, Enum):
    DIRECT = "direct"
    GROUP = "group"
    CHANNEL = "channel"
    COMMUNITY = "community"
    BROADCAST = "broadcast"


@dataclass
class Conversation:
    id: str
    type: ConversationType
    peer: UserSummary
    last_message_preview: Optional[str] = None
    unread_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, d: dict) -> "Conversation":
        peer_raw = d.get("peer") or {}
        last = d.get("last_message")
        return cls(
            id=str(d["id"]),
            type=ConversationType.DIRECT,
            peer=UserSummary.from_json(peer_raw),
            last_message_preview=last.get("content") if last else None,
            unread_count=int(d.get("unread_count") or 0),
        )
