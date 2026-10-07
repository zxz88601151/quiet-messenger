"""V1.1 Backend 统一配置入口。

Phase 2A 仅建立配置体系，不实现完整认证流程。
开发环境 secret 不得硬编码到生产配置；真实密码 / Token / Secret 不得提交。
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

Env = Literal["development", "testing", "production"]


@lru_cache
def get_settings() -> "Settings":
    return Settings()


class Settings:
    """运行时配置。优先级：环境变量 > .env > 默认值。"""

    def __init__(self) -> None:
        self.ENVIRONMENT: Env = os.getenv("ENVIRONMENT", "development")  # type: ignore[assignment]

        # --- Database ---
        # 生产使用 PostgreSQL（如 postgresql+psycopg://user:pass@host:5432/chat）。
        # 开发/CI 使用 SQLite（无需外部服务），Phase 2A 结构验证即用此。
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL", "sqlite:///./chat_dev.db"
        )

        # --- Auth（Phase 2B 才真正使用，此处仅声明，不实现流程）---
        # 生产 secret 必须通过环境变量注入，禁止硬编码。
        self.JWT_SECRET: str = os.getenv("JWT_SECRET", "")
        self.JWT_ALGORITHM: str = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
        )
        self.REFRESH_TOKEN_EXPIRE_DAYS: int = int(
            os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30")
        )

        # --- QR Login（基础设施已建表，流程在后续 Phase）---
        self.QR_SESSION_TTL_SECONDS: int = int(
            os.getenv("QR_SESSION_TTL_SECONDS", "90")
        )
        self.QR_POLL_INTERVAL_SECONDS: int = int(
            os.getenv("QR_POLL_INTERVAL_SECONDS", "3")
        )

        # --- WebSocket 实时层配置（Phase 3C 基础设施）---
        # 全部从环境变量读取，默认值保守，禁止硬编码到业务代码。
        # 鉴权超时：连接后若未在超时内完成认证（Bearer 头或第一帧），关闭。
        self.WS_AUTH_TIMEOUT_SECONDS: int = int(
            os.getenv("WS_AUTH_TIMEOUT_SECONDS", "10")
        )
        # 服务端心跳周期（server→client ping），客户端应在超时内回 pong。
        self.WS_HEARTBEAT_INTERVAL_SECONDS: int = int(
            os.getenv("WS_HEARTBEAT_INTERVAL_SECONDS", "25")
        )
        # 心跳超时：超过该时长无活动（含 pong）判定 stale 并清理。
        self.WS_HEARTBEAT_TIMEOUT_SECONDS: int = int(
            os.getenv("WS_HEARTBEAT_TIMEOUT_SECONDS", "60")
        )
        # 连接清理巡检周期（stale connection sweep）。
        self.WS_CLEANUP_INTERVAL_SECONDS: int = int(
            os.getenv("WS_CLEANUP_INTERVAL_SECONDS", "30")
        )

        # 生产环境必须存在 JWT_SECRET；否则在启动时由 main 校验。
        if self.ENVIRONMENT == "production" and not self.JWT_SECRET:
            # 不在代码中给出默认值，交由部署环境保证。
            # 这里仅记录，真正校验在 main.py 启动事件中。
            pass

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
