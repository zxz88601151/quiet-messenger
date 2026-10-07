"""Presence state (Desktop / DEF-RT-005).

Tracks friend online/offline state via WebSocket presence.update events.
Aligns with Flutter PresenceNotifier. Maintains an in-memory map of
user_id -> online bool. Only notifies listeners on actual state changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class PresenceState:
    online: dict[str, bool] = field(default_factory=dict)
    _listeners: list[Callable[["PresenceState"], None]] = field(default_factory=list)

    def subscribe(self, cb: Callable[["PresenceState"], None]) -> None:
        self._listeners.append(cb)

    def _emit(self) -> None:
        for cb in list(self._listeners):
            try:
                cb(self)
            except Exception:  # noqa: BLE001
                pass

    def is_online(self, user_id: str) -> bool:
        return self.online.get(user_id, False)


class PresenceController:
    """Subscribes to RealtimeClient presence.update events (DEF-RT-005).

    Plays online.mp3 only on genuine offline→online transitions, excluding
    the current user and duplicate/reconnect events.
    """

    def __init__(self, realtime=None, current_user_id: str = "") -> None:
        self.state = PresenceState()
        self._realtime = realtime
        self._current_user_id = current_user_id
        self._unsubscribe = None
        if realtime is not None:
            self._unsubscribe = realtime.add_event_listener(self._on_event)

    @property
    def current_user_id(self) -> str:
        return self._current_user_id

    @current_user_id.setter
    def current_user_id(self, value: str) -> None:
        self._current_user_id = value

    def _on_event(self, evt) -> None:
        if evt.type != "presence.update":
            return
        payload = evt.payload or {}
        user_id = payload.get("user_id")
        status = payload.get("status")
        if not user_id or status not in ("online", "offline"):
            return
        # Never play sound or track presence for the current user.
        if user_id == self._current_user_id:
            return
        # Initial presence sync events (sent on WS connect) must NOT trigger
        # the online sound — they represent current state, not a transition.
        is_initial = payload.get("initial", False) is True
        was_online = self.state.online.get(user_id, False)
        is_online = status == "online"
        if was_online == is_online:
            return  # no change, avoid listener noise
        self.state.online[user_id] = is_online
        # Play online sound only on genuine offline→online transition,
        # excluding initial sync events.
        if not was_online and is_online and not is_initial:
            try:
                from ...core.sound_service import SoundService
                SoundService().play_online()
            except Exception:  # noqa: BLE001
                pass
        self.state._emit()

    def dispose(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
        self.state._listeners.clear()
