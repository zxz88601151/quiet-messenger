"""ORM Model 汇总。导入即注册所有表到 Base.metadata。"""
from app.models.user import User
from app.models.device import Device
from app.models.token import RefreshToken
from app.models.qr import QRLoginSession
from app.models.friend import FriendRequest, Friendship
from app.models.conversation import Conversation, Message
from app.models.login_audit import LoginAuditLog

__all__ = [
    "User",
    "Device",
    "RefreshToken",
    "QRLoginSession",
    "FriendRequest",
    "Friendship",
    "Conversation",
    "Message",
    "LoginAuditLog",
]
