"""认证依赖（Phase 2B）。

从 Authorization: Bearer <access_token> 提取并校验当前用户。
失败抛 401（统一错误格式见 core/errors）。
"""
from __future__ import annotations

import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import unauthorized
from app.core.security import TOKEN_TYPE_ACCESS, decode_token
from app.db.base import SessionLocal
from app.models.user import User


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise unauthorized("缺少 Bearer 凭证")
    token = authorization[len("Bearer ") :].strip()
    try:
        payload = decode_token(token, TOKEN_TYPE_ACCESS)
    except Exception:
        raise unauthorized("Access Token 无效或已过期")
    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized("Token 缺少 subject")
    user = db.execute(select(User).where(User.id == uuid.UUID(user_id))).scalar_one_or_none()
    if user is None:
        raise unauthorized("用户不存在")
    return user
