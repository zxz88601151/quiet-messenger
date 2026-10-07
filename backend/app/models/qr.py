"""扫码登录会话模型（V1 核心）。

QR 仅含一次性短生命周期 session，绝不存密码 / 长期 Token。
status 七态：WAITING / SCANNED / CONFIRMED / AUTHORIZED / EXPIRED / CANCELLED / REJECTED。
QR Login Session ≠ QR Add Friend（后者属 V1.2，本阶段禁实现）。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import UUID
from app.db.base import Base


class QRLoginSession(Base):
    __tablename__ = "qr_login_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    nonce: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="WAITING", nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<QRLoginSession {self.id} {self.status}>"
