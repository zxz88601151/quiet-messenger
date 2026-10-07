"""好友 / 会话 / 消息 请求与响应 Schema（Phase 2C）。

严格对齐 shared/API_CONTRACT.md §2/§3/§4。
- 不再引入任何契约外字段。
- privacy_settings 的校验白名单与 API_CONTRACT §2 一致。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.security import (
    MESSAGE_RETENTION_VALUES,
    ONLINE_VISIBILITY_VALUES,
)
from app.schemas.user import PrivacySettings, UserPublic, to_user_public


# ---------------- User ----------------
class UserPatchRequest(BaseModel):
    """PATCH /users/me（API_CONTRACT §2）。

    可选字段，merge patch。拒绝 username / phone（契约规定 V1 默认忽略并提示不可改）。
    """

    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    avatar: str | None = Field(default=None, max_length=512)
    bio: str | None = Field(default=None, max_length=2000)
    privacy_settings: dict | None = None  # 仅 5 白名单键，service 层校验

    @field_validator("nickname")
    @classmethod
    def _strip_nickname(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError("昵称不能为空白")
        return v

    @field_validator("privacy_settings")
    @classmethod
    def _check_privacy_keys(cls, v):
        if v is None:
            return v
        allowed = {
            "read_receipt_enabled",
            "online_status_visibility",
            "typing_indicator_enabled",
            "new_device_login_alert",
            "message_retention",
        }
        unknown = set(v.keys()) - allowed
        if unknown:
            raise ValueError(f"未知隐私设置键：{', '.join(sorted(unknown))}")
        # 类型 / 取值校验
        if "read_receipt_enabled" in v and not isinstance(v["read_receipt_enabled"], bool):
            raise ValueError("read_receipt_enabled 必须为布尔")
        if "typing_indicator_enabled" in v and not isinstance(v["typing_indicator_enabled"], bool):
            raise ValueError("typing_indicator_enabled 必须为布尔")
        if "new_device_login_alert" in v and not isinstance(v["new_device_login_alert"], bool):
            raise ValueError("new_device_login_alert 必须为布尔")
        if "online_status_visibility" in v and v["online_status_visibility"] not in ONLINE_VISIBILITY_VALUES:
            raise ValueError("online_status_visibility 仅允许 all / none")
        if "message_retention" in v and v["message_retention"] not in MESSAGE_RETENTION_VALUES:
            raise ValueError("message_retention 仅允许 forever / 30_days / 1_year")
        return v


class UserSearchItem(BaseModel):
    id: str
    username: str
    nickname: str
    avatar: str | None = None


# ---------------- Friend ----------------
class FriendRequestCreate(BaseModel):
    target_username_or_phone: str = Field(..., min_length=1, max_length=32)


class FriendRequestPublic(BaseModel):
    id: str
    sender_id: str
    receiver_id: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # 对方 User 摘要（API_CONTRACT §3：请求列表含对方 User 摘要）
    sender: UserPublic | None = None
    receiver: UserPublic | None = None

    @classmethod
    def from_db(cls, req: Any, sender: Any | None = None, receiver: Any | None = None) -> "FriendRequestPublic":
        return cls(
            id=str(req.id),
            sender_id=str(req.sender_id),
            receiver_id=str(req.receiver_id),
            status=req.status,
            created_at=req.created_at,
            updated_at=req.updated_at,
            sender=to_user_public(sender) if sender else None,
            receiver=to_user_public(receiver) if receiver else None,
        )


class FriendPublic(BaseModel):
    user: UserPublic
    friendship_created_at: datetime | None = None

    @classmethod
    def from_db(cls, user: Any, created_at: Any | None) -> "FriendPublic":
        return cls(user=to_user_public(user), friendship_created_at=created_at)


class AcceptResult(BaseModel):
    friendship: FriendPublic
    conversation: "ConversationPublic"


# ---------------- Conversation / Message ----------------
class ConversationPublic(BaseModel):
    id: str
    user_a: str
    user_b: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    peer: UserPublic | None = None
    last_message: "MessagePublic | None" = None
    unread_count: int = 0

    @classmethod
    def from_db(
        cls,
        conv: Any,
        peer: Any | None = None,
        last_message: Any | None = None,
        unread_count: int = 0,
    ) -> "ConversationPublic":
        return cls(
            id=str(conv.id),
            user_a=str(conv.user_a),
            user_b=str(conv.user_b),
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            peer=to_user_public(peer) if peer else None,
            last_message=MessagePublic.from_db(last_message) if last_message else None,
            unread_count=unread_count,
        )


class MessagePublic(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    client_message_id: str | None = None
    content: str
    created_at: datetime | None = None
    read_at: datetime | None = None

    @classmethod
    def from_db(cls, msg: Any) -> "MessagePublic":
        return cls(
            id=str(msg.id),
            conversation_id=str(msg.conversation_id),
            sender_id=str(msg.sender_id),
            client_message_id=msg.client_message_id,
            content=msg.content,
            created_at=msg.created_at,
            read_at=msg.read_at,
        )


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    client_message_id: str = Field(..., min_length=1, max_length=64)


class MessagePage(BaseModel):
    items: list[MessagePublic]
    next_cursor: str = ""


# 解决前向引用
AcceptResult.model_rebuild()
ConversationPublic.model_rebuild()
