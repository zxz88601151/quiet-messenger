"""设备模型（V1 核心）。

User 与 Device 分离。一个 User 可拥有多个 Device。
服务端不存储 sync_status（客户端推导态）。
device_type 仅 mobile / desktop 两档。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import UUID
from app.db.base import Base
from sqlalchemy import UniqueConstraint


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_type: Mapped[str] = mapped_column(String(16), nullable=False)  # mobile|desktop
    device_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_identifier: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 联合唯一：同一用户 + 同一稳定标识，防重复登记。
    __table_args__ = (
        UniqueConstraint("user_id", "device_identifier", name="uq_devices_user_identifier"),
    )

    def __repr__(self) -> str:
        return f"<Device {self.device_name} ({self.device_type})>"
