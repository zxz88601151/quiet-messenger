"""认证依赖（Phase 2B）。

从 Authorization: Bearer <access_token> 提取并校验当前用户。
失败抛 401（统一错误格式见 core/errors）。
"""
from __future__ import annotations

import uuid

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import rate_limited, unauthorized
from app.core.rate_limiter import (
    POLICY_FORGOT_PASSWORD,
    POLICY_RESET_PASSWORD,
    limiter,
)
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


def get_client_ip(request: Request) -> str:
    """取客户端 IP（限流 key 用）。注：经过可信反代时应改读 X-Forwarded-For。"""
    return request.client.host if request.client else "unknown"


async def _phone_from_body(request: Request) -> str:
    """从请求体提取 phone（request.json() 有缓存，不影响端点再次解析 body）。"""
    try:
        body = await request.json()
        return str(body.get("phone") or "")
    except Exception:
        return ""


async def rate_limit_forgot_password(request: Request) -> None:
    """S-2 修复：POST /auth/forgot-password — 5 次 / 10 分钟 / IP+phone。

    IP+phone 双 key：既防单 IP 横扫号段滥发短信（费用攻击），
    也防多 IP 针对同一号码滥发。
    """
    key = f"forgot_password:{get_client_ip(request)}:{await _phone_from_body(request)}"
    if not limiter.check(key, POLICY_FORGOT_PASSWORD):
        raise rate_limited("获取验证码过于频繁，请 10 分钟后再试")


async def rate_limit_reset_password(request: Request) -> None:
    """S-2 修复：POST /auth/reset-password — 20 次 / 10 分钟 / IP+phone。

    6 位重置码仅 100 万空间，无限流时可被在线爆破；此处是主防线。
    纵深：_ResetCodeStore.verify 另有连续失败计数（10 次直接作废当前 code）。
    """
    key = f"reset_password:{get_client_ip(request)}:{await _phone_from_body(request)}"
    if not limiter.check(key, POLICY_RESET_PASSWORD):
        raise rate_limited("重置尝试过于频繁，请 10 分钟后再试")
