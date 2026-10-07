"""Realtime connection states (Desktop / PySide6, Phase 3C).

Mirrors the backend ConnectionState enum. Client-only view includes
RECONNECTING (client-driven backoff) which the server does not track.
"""
from __future__ import annotations

from enum import Enum


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"

    @property
    def is_connected(self) -> bool:
        return self is ConnectionState.CONNECTED

    @property
    def is_terminal_error(self) -> bool:
        return self is ConnectionState.ERROR
