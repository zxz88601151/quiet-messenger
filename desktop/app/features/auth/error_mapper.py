"""Auth error mapping (Desktop / PySide6).

Translates the backend ``ApiException`` (code-based) into user-facing
messages. Per Phase 3B §10 the UI must never show raw exceptions / HTTP
details / stack traces.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...errors.api_exception import ApiException


@dataclass
class AuthError:
    message: str
    code: str | None = None


def map_auth_error(e: ApiException) -> AuthError:
    code = e.code
    if code == "INVALID_CREDENTIALS":
        return AuthError(message="用户名或密码错误，请重试", code=code)
    if code == "VALIDATION_ERROR":
        msg = e.message if e.message else "请检查输入项是否合法"
        return AuthError(message=f"输入有误：{msg}" if e.message else msg, code=code)
    if code in ("UNAUTHENTICATED", "FORBIDDEN"):
        return AuthError(message="登录已失效，请重新登录", code=code)
    if code == "NETWORK_ERROR":
        return AuthError(message="网络异常，请检查连接后重试", code=code)
    return AuthError(message=e.message if e.message else "操作失败，请稍后重试", code=code)
