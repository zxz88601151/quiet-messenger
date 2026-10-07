"""登录审计日志模型（V1.1 安全审计）。

记录所有登录/登出/登录失败事件，用于：
- 异常登录检测（异地登录、频繁失败）
- 安全审计追溯
- 用户登录设备历史

不存储密码、token 明文。仅存标识符和元数据。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.user import UUID
from app.db.base import Base


class LoginAuditLog(Base):
    __tablename__ = "login_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4
    )
    # 关联用户（登录失败时可能为 null，因为用户未找到）
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 登录时使用的标识符（username 或 phone）
    identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 动作类型：login_success / login_failure / logout
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 失败原因（仅 login_failure）：invalid_credentials / user_not_found / error
    failure_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 设备信息
    device_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 网络信息
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    def __repr__(self) -> str:
        return f"<LoginAuditLog {self.action} {self.identifier}>"
