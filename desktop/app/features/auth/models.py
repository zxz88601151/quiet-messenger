"""Auth domain models (Desktop / PySide6).

Mirrors the backend `UserPublic` / token response (shared/API_CONTRACT.md
§1, §2). Only fields needed for Phase 3B auth/session are modeled — no
friend/message/presence fields (scope discipline).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class User:
    id: str
    username: str
    phone: str
    nickname: str
    avatar: str | None = None
    bio: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "User":
        return cls(
            id=str(data["id"]),
            username=data["username"],
            phone=data["phone"],
            nickname=data["nickname"],
            avatar=data.get("avatar"),
            bio=data.get("bio"),
        )


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "AuthTokens":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
        )


@dataclass
class Session:
    user: User
    tokens: AuthTokens


@dataclass
class DeviceInfo:
    device_type: str = "desktop"
    device_name: str = "Desktop"
    device_identifier: str = "pyside6-desktop-default"

    def to_json(self) -> dict[str, Any]:
        return {
            "device_type": self.device_type,
            "device_name": self.device_name,
            "device_identifier": self.device_identifier,
        }
