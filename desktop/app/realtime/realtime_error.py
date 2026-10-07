"""Realtime errors (Desktop / PySide6, Phase 3C).

Distinct from ApiException (REST). Carries a safe, user-facing message —
never leaks raw tokens / stack traces / protocol internals.
"""
from __future__ import annotations


class RealtimeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:  # 不泄露 token / 内部细节
        return f"[{self.code}] {self.message}"


class AuthFailedError(RealtimeError):
    def __init__(self, message: str = "实时连接认证失败，请重新登录") -> None:
        super().__init__("WS_AUTH_FAILED", message)


class ConnectionLostError(RealtimeError):
    def __init__(self, message: str = "实时连接已断开") -> None:
        super().__init__("WS_CONNECTION_LOST", message)
