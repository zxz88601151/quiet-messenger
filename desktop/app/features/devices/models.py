"""Device domain model (Desktop / PySide6).

Mirrors backend DevicePublic (shared/API_CONTRACT §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Device:
    id: str
    user_id: str
    device_type: str
    device_name: str | None = None
    device_identifier: str | None = None
    last_active_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None
    is_current: bool = False

    @property
    def is_online(self) -> bool:
        """A device is considered online if it has not been revoked."""
        return self.revoked_at is None

    @property
    def display_name(self) -> str:
        return self.device_name or self.device_type or "Unknown Device"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Device":
        def _parse_dt(v: Any) -> datetime | None:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None

        return cls(
            id=str(data["id"]),
            user_id=str(data.get("user_id", "")),
            device_type=data.get("device_type", "unknown"),
            device_name=data.get("device_name"),
            device_identifier=data.get("device_identifier"),
            last_active_at=_parse_dt(data.get("last_active_at")),
            created_at=_parse_dt(data.get("created_at")),
            revoked_at=_parse_dt(data.get("revoked_at")),
            is_current=bool(data.get("is_current", False)),
        )
