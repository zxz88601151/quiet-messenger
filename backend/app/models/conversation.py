"""会话与消息模型（V1）。

Conversation 一对一规范化：user_a = min(u1,u2), user_b = max(u1,u2)，
UNIQUE(user_a, user_b) 杜绝重复会话。
Message 服务端**不存 status 字段**；仅 client_message_id（幂等）+ read_at（已读）。
禁止新增 status / delivered / queued 等字段。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import UUID
from app.db.base import Base
from sqlalchemy import Text, UniqueConstraint


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    user_a: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_b: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 唯一约束：UNIQUE(user_a, user_b) —— 一对用户仅一个会话，杜绝 A-B / A-B / A-B 重复。
    __table_args__ = (
        UniqueConstraint("user_a", "user_b", name="uq_conversations_pair"),
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.user_a}-{self.user_b}>"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_message_id: Mapped[str] = mapped_column(String(64), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 注意：服务端 Message 无 status 字段（V1.1 冻结）。
    # UNIQUE(conversation_id, client_message_id) 防重试重复。
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "client_message_id", name="uq_messages_conv_client"
        ),
    )

    def __repr__(self) -> str:
        return f"<Message {self.id} conv={self.conversation_id}>"
