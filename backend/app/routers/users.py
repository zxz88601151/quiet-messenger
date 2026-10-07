"""User 路由（Phase 2C，API_CONTRACT §2）。

GET /users/me / PATCH /users/me / GET /users/search。
严格不实现：独立的 /privacy 端点（privacy 仅通过 PATCH /users/me 合并更新）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.social import UserPatchRequest
from app.services import social_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
def get_me(user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.get_me(user)


@router.patch("/me")
def patch_me(
    data: UserPatchRequest,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    payload = data.model_dump(exclude_unset=True)
    return social_service.patch_me(user, payload, db)


@router.get("/search")
def search_users(
    q: str = Query(default="", max_length=64),
    limit: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return social_service.search_users(q, db, limit=limit)
