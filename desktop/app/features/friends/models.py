"""Friend domain models (Desktop / PySide6, Phase 3D).

Mirror backend `UserSearchItem` / `FriendRequestPublic` / `FriendPublic`
(API_CONTRACT §2/§3). Only privacy-safe, public fields are modeled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class FriendStatus(str, Enum):
    NONE = "none"
    PENDING_OUTGOING = "pending_outgoing"
    PENDING_INCOMING = "pending_incoming"
    FRIENDS = "friends"
    BLOCKED = "blocked"


@dataclass
class UserSummary:
    id: str
    username: str
    nickname: str
    avatar: Optional[str] = None

    @classmethod
    def from_json(cls, d: dict) -> "UserSummary":
        return cls(
            id=str(d["id"]),
            username=d.get("username", ""),
            nickname=d.get("nickname", ""),
            avatar=d.get("avatar"),
        )


@dataclass
class FriendRequest:
    id: str
    sender_id: str
    receiver_id: str
    status: str
    is_incoming: bool
    other_user: Optional[UserSummary] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, d: dict, viewer_id: str) -> "FriendRequest":
        sender = d.get("sender") or {}
        receiver = d.get("receiver") or {}
        other_raw = sender if sender.get("id") != viewer_id else receiver
        other = UserSummary.from_json(other_raw) if other_raw else None
        return cls(
            id=str(d["id"]),
            sender_id=str(d["sender_id"]),
            receiver_id=str(d["receiver_id"]),
            status=d["status"],
            is_incoming=d.get("receiver_id") == viewer_id,
            other_user=other,
        )


@dataclass
class Friendship:
    user: UserSummary
    friendship_created_at: Optional[datetime] = None

    @classmethod
    def from_json(cls, d: dict) -> "Friendship":
        user_raw = d.get("user") or {}
        created = d.get("friendship_created_at")
        return cls(
            user=UserSummary.from_json(user_raw),
            friendship_created_at=_maybe_dt(created),
        )


@dataclass
class AcceptResult:
    friendship: Friendship
    conversation_id: str


def _maybe_dt(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
