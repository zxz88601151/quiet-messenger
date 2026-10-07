"""Friend error mapping (Desktop / PySide6, Phase 3D).

Translates backend `code` (API_CONTRACT §7 + social_service) to a user-facing
message. UI must NEVER show raw HTTP/traceback detail.
"""
from __future__ import annotations

from dataclasses import dataclass

from ...errors.api_exception import ApiException


@dataclass
class FriendError:
    message: str
    code: str


def map_friend_error(e: ApiException) -> FriendError:
    return _TABLE.get(e.code, FriendError(message=e.message or "操作失败，请稍后重试", code=e.code))


_TABLE = {
    "FRIEND_NOT_FOUND": FriendError("好友请求不存在", "FRIEND_NOT_FOUND"),
    "DUPLICATE_REQUEST": FriendError("该好友请求已存在", "DUPLICATE_REQUEST"),
    "FRIEND_REQUIRED": FriendError("双方需为好友关系", "FRIEND_REQUIRED"),
    "CONVERSATION_FORBIDDEN": FriendError("无权访问该会话", "CONVERSATION_FORBIDDEN"),
    "CONFLICT": FriendError("操作状态冲突，请刷新后重试", "CONFLICT"),
    "VALIDATION_ERROR": FriendError("输入有误", "VALIDATION_ERROR"),
    "UNAUTHENTICATED": FriendError("登录已失效，请重新登录", "UNAUTHENTICATED"),
    "FORBIDDEN": FriendError("登录已失效，请重新登录", "FORBIDDEN"),
    "NETWORK_ERROR": FriendError("网络异常，请检查连接后重试", "NETWORK_ERROR"),
}
