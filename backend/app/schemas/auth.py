"""Auth 请求/响应 Schema（Phase 2B）。

严格对齐 shared/API_CONTRACT.md §1 Auth。
长度/格式校验以 Contract 为准（username 32 / phone 20 / password 等）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.security import DEVICE_TYPES


def _strip(v: str) -> str:
    return v.strip() if isinstance(v, str) else v


class DeviceInput(BaseModel):
    device_type: str = Field(..., description="mobile | desktop")
    device_name: str | None = Field(default=None, max_length=64)
    device_identifier: str | None = Field(default=None, max_length=255)

    @field_validator("device_type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        v = _strip(v)
        if v not in DEVICE_TYPES:
            raise ValueError("device_type 必须为 mobile 或 desktop")
        return v

    @field_validator("device_name", "device_identifier")
    @classmethod
    def _strip_str(cls, v):
        return _strip(v) if isinstance(v, str) else v


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    phone: str = Field(..., min_length=6, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    nickname: str = Field(..., min_length=1, max_length=32)
    device: DeviceInput | None = None  # 可选；缺失时自动建默认 mobile device

    @field_validator("username", "phone", "nickname", "password")
    @classmethod
    def _strip(cls, v):
        s = _strip(v)
        if s == "":
            raise ValueError("不能为空白字符串")
        return s

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        if not v.isdigit():
            raise ValueError("phone 必须为数字")
        return v


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=32)
    password: str = Field(..., min_length=1, max_length=128)
    device: DeviceInput

    @field_validator("identifier", "password")
    @classmethod
    def _strip(cls, v):
        s = _strip(v)
        if s == "":
            raise ValueError("不能为空白字符串")
        return s


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        v = _strip(v)
        if not v.isdigit():
            raise ValueError("phone 必须为数字")
        return v


class ResetPasswordRequest(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20)
    code: str = Field(..., min_length=1, max_length=32)
    new_password: str = Field(..., min_length=6, max_length=128)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        v = _strip(v)
        if not v.isdigit():
            raise ValueError("phone 必须为数字")
        return v

    @field_validator("new_password")
    @classmethod
    def _strip_pw(cls, v):
        s = _strip(v)
        if s == "":
            raise ValueError("不能为空白字符串")
        return s


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
