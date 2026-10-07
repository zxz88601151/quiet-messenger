"""Presence service — tracks user online/offline state and notifies friends.

Infrastructure only: tracks connection count per user, pushes presence.update
WS events to friends when a user's first connection opens (online) or last
connection closes (offline). Does NOT store presence in DB (in-memory only,
single-process). Multi-worker deployments need Redis pub/sub (Phase 5+).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.friend import Friendship
from app.services.connection_manager import manager, make_event


class PresenceService:
    """Tracks online users and notifies friends of presence changes."""

    def __init__(self) -> None:
        # In-memory online set (single process only).
        self._online: set[str] = set()

    def is_online(self, user_id: str) -> bool:
        return user_id in self._online

    def get_online_users(self) -> set[str]:
        return set(self._online)

    def get_online_friend_ids(self, user_id: str, db: Session) -> list[str]:
        """Get friend user IDs who are currently online.

        Used for initial presence sync on WebSocket connect — sends the
        current online state of all friends so the client doesn't show
        already-online friends as offline (Initial Presence Sync Gap fix).
        """
        friend_ids = self._get_friend_ids(user_id, db)
        return [fid for fid in friend_ids if fid in self._online]

    async def on_connect(self, user_id: str, db: Session) -> None:
        """Called after a user's WebSocket connection is registered.

        If this is the user's first connection (was offline), mark online and
        notify all friends via presence.update WS event.
        """
        was_offline = user_id not in self._online
        self._online.add(user_id)
        if was_offline:
            await self._notify_friends(user_id, "online", db)

    async def on_disconnect(self, user_id: str, db: Session) -> None:
        """Called after a user's WebSocket connection is removed.

        If the user has no more connections, mark offline and notify friends.
        """
        if manager.user_connection_count(user_id) == 0:
            self._online.discard(user_id)
            await self._notify_friends(user_id, "offline", db)

    def _get_friend_ids(self, user_id: str, db: Session) -> list[str]:
        """Get all friend user IDs for a user.

        Returns strings (not uuid.UUID) because connection_manager keys and
        presence._online set use str user_ids. UUID != str would silently
        break both `fid in self._online` and `manager.send_to_user(fid)`.
        """
        rows = db.execute(
            select(Friendship.friend_id).where(Friendship.user_id == user_id)
        ).scalars().all()
        return [str(r) for r in rows]

    async def _notify_friends(
        self, user_id: str, status: str, db: Session
    ) -> None:
        """Push presence.update event to all friends of the user."""
        friend_ids = self._get_friend_ids(user_id, db)
        event = make_event("presence.update", {
            "user_id": user_id,
            "status": status,
        })
        for fid in friend_ids:
            await manager.send_to_user(fid, event)


# Global singleton (single process).
presence = PresenceService()
