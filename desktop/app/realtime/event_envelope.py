"""Unified WebSocket event envelope (Desktop / PySide6, Phase 3C).

Matches backend make_event():
    { "type": str, "id": str, "timestamp": str, "payload": dict }

Server→Client (Phase 3C): connection.authenticated / connection.ready /
  connection.ping / connection.error
Client→Server: connection.auth / connection.pong / connection.close

Only infrastructure events are modeled. Business events (message.* / friend.*
/ conversation.* / handoff.*) are NOT defined here — they belong to later phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventEnvelope:
    type: str
    id: str = ""
    timestamp: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "EventEnvelope":
        """Parse with full field type-safety (DEF-RT-007 / aligns with
        Flutter DEFECT-001/002/003).

        - Missing field (None) → compatible default (matches existing behavior).
        - Non-null but wrong type → raise ValueError (malformed envelope);
          the caller (RealtimeClient._loop) catches and discards the frame.
        """
        raw_type = data.get("type")
        raw_id = data.get("id")
        raw_timestamp = data.get("timestamp")
        raw_payload = data.get("payload")

        if raw_type is not None and not isinstance(raw_type, str):
            raise ValueError(
                f"EventEnvelope.type must be str or None, got {type(raw_type).__name__}"
            )
        if raw_id is not None and not isinstance(raw_id, str):
            raise ValueError(
                f"EventEnvelope.id must be str or None, got {type(raw_id).__name__}"
            )
        if raw_timestamp is not None and not isinstance(raw_timestamp, str):
            raise ValueError(
                f"EventEnvelope.timestamp must be str or None, got {type(raw_timestamp).__name__}"
            )
        if raw_payload is not None and not isinstance(raw_payload, dict):
            raise ValueError(
                f"EventEnvelope.payload must be dict or None, got {type(raw_payload).__name__}"
            )

        return cls(
            type=raw_type or "",
            id=raw_id or "",
            timestamp=raw_timestamp or "",
            payload=raw_payload or {},
        )

    @classmethod
    def pong(cls) -> dict[str, Any]:
        return {"type": "connection.pong"}

    @classmethod
    def close(cls) -> dict[str, Any]:
        return {"type": "connection.close"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
