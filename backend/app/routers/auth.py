"""Auth 路由（Phase 2B）。

端点（基准 /api/v1）：
POST /auth/register
POST /auth/login
POST /auth/refresh
POST /auth/logout
POST /auth/forgot-password
POST /auth/reset-password

严格服从 API_CONTRACT §1。无 Friend/Message/WS/QR Add Friend。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.config import get_settings
from app.core.deps import get_db
from app.core.errors import validation_error
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    LogoutRequest,
)
from app.schemas.user import to_device_public, to_user_public
from app.services import auth_service

settings = get_settings()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db=Depends(get_db)):
    user, device, access, refresh = auth_service.register(db, data)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "user": to_user_public(user).model_dump(mode="json"),
        "device": to_device_public(device).model_dump(mode="json"),
    }


@router.post("/login")
def login(data: LoginRequest, request: Request, db=Depends(get_db)):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    result = auth_service.login(
        db, data, ip_address=client_ip, user_agent=user_agent
    )
    if result is None:
        # 实际不会到这（service 抛异常），保留防御
        raise validation_error("登录失败")
    user, device, access, refresh = result
    return {
        "access_token": access,
        "refresh_token": refresh,
        "user": to_user_public(user).model_dump(mode="json"),
        "device": to_device_public(device).model_dump(mode="json"),
    }


@router.post("/refresh")
def refresh(data: RefreshRequest):
    user, device, access, new_refresh = auth_service.refresh(data.refresh_token)
    return {"access_token": access, "refresh_token": new_refresh}


@router.post("/logout")
def logout(data: LogoutRequest, request: Request):
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    auth_service.logout(
        data.refresh_token, ip_address=client_ip, user_agent=user_agent
    )
    return {"ok": True}


@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db=Depends(get_db)):
    ok, dev_code = auth_service.forgot_password(
        db, data.phone, dev_mode=settings.ENVIRONMENT != "production"
    )
    resp = {"ok": ok}
    if dev_code is not None:
        resp["dev_code"] = dev_code  # 仅 Dev 返回，生产接短信不返回
    return resp


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db=Depends(get_db)):
    ok = auth_service.reset_password(db, data.phone, data.code, data.new_password)
    if not ok:
        # 不区分"账号不存在"与"code 错误"以防水枚举；统一 400 VALIDATION_ERROR
        raise validation_error("验证码无效或已使用")
    return {"ok": True}
