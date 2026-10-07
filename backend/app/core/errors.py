"""统一错误响应（API_CONTRACT §7）。

格式：{ "error": { "code": "...", "message": "...", "status": <http> } }
常用 code：UNAUTHENTICATED / FORBIDDEN / VALIDATION_ERROR / DUPLICATE_USER 等。
"""
from __future__ import annotations

from fastapi import HTTPException, status


def error_response(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message, "status": http_status}},
    )


def unauthorized(message: str = "未认证或凭证无效") -> HTTPException:
    return error_response("UNAUTHENTICATED", message, status.HTTP_401_UNAUTHORIZED)


def forbidden(message: str = "无权限") -> HTTPException:
    return error_response("FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


def validation_error(message: str = "请求校验失败") -> HTTPException:
    return error_response("VALIDATION_ERROR", message, status.HTTP_400_BAD_REQUEST)


def duplicate_user(message: str = "用户名或手机号已存在") -> HTTPException:
    return error_response("DUPLICATE_USER", message, status.HTTP_409_CONFLICT)


def rate_limited(message: str = "请求过于频繁，请稍后再试") -> HTTPException:
    """安全补丁 S-2 / H-3：限流拒绝（429）。"""
    return error_response("RATE_LIMITED", message, status.HTTP_429_TOO_MANY_REQUESTS)


def not_found(message: str = "资源不存在") -> HTTPException:
    return error_response("NOT_FOUND", message, status.HTTP_404_NOT_FOUND)


def invalid_credentials(message: str = "账号或密码错误") -> HTTPException:
    # 与 login 失败统一语义，不区分账号/密码以防水枚举（契约 §5/§11）。
    return error_response("INVALID_CREDENTIALS", message, status.HTTP_401_UNAUTHORIZED)


def friend_not_found(message: str = "好友请求不存在") -> HTTPException:
    return error_response("FRIEND_NOT_FOUND", message, status.HTTP_404_NOT_FOUND)


def friend_required(message: str = "双方必须为好友关系") -> HTTPException:
    # 发消息前置校验 Friendship 缺失 → 403（API_CONTRACT §4）。
    return error_response("FRIEND_REQUIRED", message, status.HTTP_403_FORBIDDEN)


def conversation_forbidden(message: str = "无权访问该会话") -> HTTPException:
    # 越权访问会话 → 403（API_CONTRACT §4）。
    return error_response("CONVERSATION_FORBIDDEN", message, status.HTTP_403_FORBIDDEN)


def duplicate_request(message: str = "好友请求已存在") -> HTTPException:
    return error_response("DUPLICATE_REQUEST", message, status.HTTP_409_CONFLICT)


def conflict(message: str = "资源状态冲突") -> HTTPException:
    return error_response("CONFLICT", message, status.HTTP_409_CONFLICT)
