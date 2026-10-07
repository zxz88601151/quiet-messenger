"""安全工具（Phase 2B 实现）。

- 密码：bcrypt 哈希 + 校验（禁止明文/MD5/SHA*）。
- JWT：Access Token（短效）+ Refresh Token（可吊销、轮换）。
- token 哈希：refresh token 只存 SHA-256 哈希。
- secret 从配置读取，禁止硬编码。

Privacy/Device/Now 常量保留供后续 Phase 使用。
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt
from sqlalchemy import select

from app.config import get_settings
from app.db.base import SessionLocal
from app.models.token import RefreshToken
from app.models.user import User

# --- 常量（V1.1 冻结，禁止新增）---
PRIVACY_KEYS = (
    "read_receipt_enabled",
    "online_status_visibility",
    "typing_indicator_enabled",
    "new_device_login_alert",
    "message_retention",
)
ONLINE_VISIBILITY_VALUES = ("all", "none")
MESSAGE_RETENTION_VALUES = ("forever", "30_days", "1_year")
DEVICE_TYPES = ("mobile", "desktop")
NOW_STATES = ("online", "dnd", "offline")

# Token 类型声明（claim: type）
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

settings = get_settings()


# ---------------- 密码 ----------------
def hash_password(password: str) -> str:
    """bcrypt 哈希。返回需存储的 password_hash。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """安全校验密码。恒定时间比较由 bcrypt.checkpw 保证。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- Refresh Token ----------------
def generate_refresh_token() -> tuple[str, str]:
    """生成 refresh token 明文 + 其 SHA-256 哈希（仅哈希落库）。"""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------- JWT ----------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(user_id: str, device_id: str | None = None) -> str:
    """签发 Access Token（短效）。"""
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TOKEN_TYPE_ACCESS,
        "iat": _now(),
        "exp": _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if device_id:
        payload["device_id"] = str(device_id)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token_record(
    user_id: str, device_id: str, family_id: uuid.UUID | None = None
) -> tuple[str, str]:
    """签发 refresh token：落库哈希 + 返回明文。

    返回 (raw_token, token_hash)。明文仅本次返回给客户端，库内只存哈希。
    H-1：family_id 用于轮换链追踪；不传则新起一个 family。
    """
    raw, token_hash = generate_refresh_token()
    expires_at = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    with SessionLocal() as db:
        rec = RefreshToken(
            user_id=uuid.UUID(str(user_id)),
            device_id=uuid.UUID(str(device_id)),
            token_hash=token_hash,
            expires_at=expires_at,
            revoked=False,
            family_id=family_id or uuid.uuid4(),
        )
        db.add(rec)
        db.commit()
    return raw, token_hash


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """校验并解码 JWT。失败抛 jwt 异常（调用方映射为 401）。"""
    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"unexpected token type: {payload.get('type')}")
    return payload


def _revoke_by_hash(db, token_hash: str) -> None:
    """按哈希吊销（H-1：同时记录 revoked_at，供复用检测宽限判断）。"""
    rec = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    ).scalar_one_or_none()
    if rec is not None and not rec.revoked:
        rec.revoked = True
        rec.revoked_at = _now()


def revoke_refresh_token(raw_token: str) -> None:
    """吊销 refresh token（明文 → 哈希 → 置 revoked + revoked_at）。"""
    token_hash = hash_token(raw_token)
    with SessionLocal() as db:
        _revoke_by_hash(db, token_hash)
        db.commit()


def revoke_token_family(db, family_id: uuid.UUID) -> int:
    """H-1 熔断：吊销同一 family 下全部 token。返回被吊销数量。"""
    now = _now()
    recs = db.execute(
        select(RefreshToken).where(
            RefreshToken.family_id == family_id, RefreshToken.revoked.is_(False)
        )
    ).scalars().all()
    for rec in recs:
        rec.revoked = True
        rec.revoked_at = now
    return len(recs)


def get_live_family_token(db, family_id: uuid.UUID) -> RefreshToken | None:
    """H-1：取 family 内最新（created_at 倒序）的有效 token，用于宽限内重试签发。"""
    return db.execute(
        select(RefreshToken)
        .where(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > _now(),
        )
        .order_by(RefreshToken.created_at.desc())
    ).scalar_one_or_none()


def verify_refresh_token(raw_token: str) -> RefreshToken | None:
    """校验 refresh token（不透明随机串，仅哈希落库，不是 JWT）。

    校验链：哈希存在 + 未吊销 + 未过期。
    返回有效的 RefreshToken 记录，否则 None。
    """
    rec, status = verify_refresh_token_with_status(raw_token)
    return rec if status == "valid" else None


def verify_refresh_token_with_status(raw_token: str) -> tuple[RefreshToken | None, str]:
    """H-1：带状态的校验。

    返回 (记录, 状态)，状态 ∈ {"valid", "revoked", "expired", "not_found"}。
    注意：返回的 rec 绑定在已关闭的 session 上，仅可安全读取已加载的列属性
    （id / user_id / device_id / family_id / revoked / revoked_at / expires_at）；
    需要写操作时调用方应重新查询。
    """
    token_hash = hash_token(raw_token)
    with SessionLocal() as db:
        rec = db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()
        if rec is None:
            return None, "not_found"
        if rec.revoked:
            return rec, "revoked"
        if rec.expires_at.replace(tzinfo=timezone.utc) < _now():
            return None, "expired"
        return rec, "valid"
