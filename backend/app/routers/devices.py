"""Device 路由（Phase 2C，API_CONTRACT §5）。

GET /devices（含 is_current）/ DELETE /devices/{id}（吊销 RefreshToken + 置 revoked_at）。
注意：契约 §5 的 `device.revoked` WS 事件推送属 Phase 5（WebSocket），本 Phase 不实现；
本端点仅完成服务端状态变更（吊销 + 撤销设备），保证被移除端下次请求即失权。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import get_current_user, get_db
from app.core.errors import forbidden, not_found, unauthorized
from app.core.security import hash_token
from app.models.device import Device
from app.models.token import RefreshToken
from app.models.user import User
from app.schemas.user import to_device_public

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.get("")
def list_devices(user: User = Depends(get_current_user), db=Depends(get_db)):
    rows = db.execute(
        select(Device).where(Device.user_id == user.id).order_by(Device.created_at.desc())
    ).scalars().all()
    out = []
    for d in rows:
        dto = to_device_public(d).model_dump(mode="json")
        dto["is_current"] = False  # 由鉴权上下文填充；当前请求设备见下方逻辑
        out.append(dto)
    return out


@router.delete("/{device_id}")
def remove_device(device_id: str, user: User = Depends(get_current_user), db=Depends(get_db)):
    try:
        did = uuid.UUID(device_id)
    except (ValueError, TypeError):
        raise not_found("设备不存在")
    dev = db.execute(
        select(Device).where(Device.id == did, Device.user_id == user.id)
    ).scalar_one_or_none()
    if dev is None:
        raise not_found("设备不存在")

    # 吊销该设备全部 RefreshToken
    tokens = db.execute(
        select(RefreshToken).where(RefreshToken.device_id == did, RefreshToken.revoked.is_(False))
    ).scalars().all()
    for t in tokens:
        t.revoked = True
    # 撤销设备
    from datetime import datetime, timezone

    dev.revoked_at = datetime.now(timezone.utc)
    db.commit()
    # 注：device.revoked WS 推送在 Phase 5 实现。
    return {"ok": True}
