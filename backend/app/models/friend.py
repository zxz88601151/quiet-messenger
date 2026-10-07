"""好友请求与好友关系模型（V1）。

FriendRequest 与 Friendship 必须分离，不能合并为 boolean。
FriendRequest.status：pending / accepted / rejected。
Friendship 接受时双向写入 (A→B) 与 (B→A)。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import UUID
from app.db.base import Base
from sqlalchemy import UniqueConstraint


class FriendRequest(Base):
    __tablename__ = "friend_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receiver_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 唯一约束：UNIQUE(sender_id, receiver_id) —— 防止重复请求（同一方向）。
    __table_args__ = (
        UniqueConstraint("sender_id", "receiver_id", name="uq_friend_requests_pair"),
    )

    def __repr__(self) -> str:
        return f"<FriendRequest {self.sender_id}->{self.receiver_id} {self.status}>"


class Friendship(Base):
    __tablename__ = "friendships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    friend_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 唯一约束：UNIQUE(user_id, friend_id) —— 防重复好友。
    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friendships_pair"),
    )

    def __repr__(self) -> str:
        return f"<Friendship {self.user_id}-{self.friend_id}>"
