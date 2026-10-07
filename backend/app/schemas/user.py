"""User / Device 公共响应 Schema（Phase 2B）。

不暴露 password_hash（API_CONTRACT §2 GET /users/me）。
privacy_settings 始终返回完整 5 键。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PrivacySettings(BaseModel):
    read_receipt_enabled: bool = True
    online_status_visibility: str = "all"
    typing_indicator_enabled: bool = True
    new_device_login_alert: bool = True
    message_retention: str = "forever"

    @classmethod
    def from_db(cls, raw: dict | None) -> "PrivacySettings":
        if not raw:
            return cls()
        data = {
            "read_receipt_enabled": raw.get("read_receipt_enabled", True),
            "online_status_visibility": raw.get("online_status_visibility", "all"),
            "typing_indicator_enabled": raw.get("typing_indicator_enabled", True),
            "new_device_login_alert": raw.get("new_device_login_alert", True),
            "message_retention": raw.get("message_retention", "forever"),
        }
        return cls(**data)


class UserPublic(BaseModel):
    id: str
    username: str
    phone: str
    nickname: str
    avatar: str | None = None
    bio: str | None = None
    privacy_settings: PrivacySettings
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DevicePublic(BaseModel):
    id: str
    user_id: str
    device_type: str
    device_name: str | None = None
    device_identifier: str | None = None
    last_active_at: datetime | None = None
    created_at: datetime | None = None
    revoked_at: datetime | None = None


class AuthResult(BaseModel):
    access_token: str
    refresh_token: str
    user: UserPublic
    device: DevicePublic


def to_user_public(user: Any) -> UserPublic:
    return UserPublic(
        id=str(user.id),
        username=user.username,
        phone=user.phone,
        nickname=user.nickname,
        avatar=user.avatar,
        bio=user.bio,
        privacy_settings=PrivacySettings.from_db(user.privacy_settings),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def to_device_public(device: Any) -> DevicePublic:
    return DevicePublic(
        id=str(device.id),
        user_id=str(device.user_id),
        device_type=device.device_type,
        device_name=device.device_name,
        device_identifier=device.device_identifier,
        last_active_at=device.last_active_at,
        created_at=device.created_at,
        revoked_at=device.revoked_at,
    )
