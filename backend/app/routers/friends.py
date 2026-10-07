"""Friend 路由（Phase 2C，API_CONTRACT §3）。

POST /friends/requests / GET /friends/requests / accept / reject / GET /friends / DELETE /friends/{id}。
严格不实现：QR Add Friend（POSTPONE #2）、陌生人推荐、社交发现。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.social import FriendRequestCreate
from app.services import social_service

router = APIRouter(prefix="/api/v1/friends", tags=["friends"])


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(
    data: FriendRequestCreate,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await social_service.create_friend_request(user, data.target_username_or_phone, db)


@router.get("/requests")
def list_requests(
    type: str = "all",
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    if type not in ("incoming", "outgoing", "all"):
        type = "all"
    return social_service.list_friend_requests(user, type, db)


@router.post("/requests/{request_id}/accept")
def accept_request(request_id: str, user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.accept_friend_request(user, request_id, db)


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: str, user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.reject_friend_request(user, request_id, db)


@router.get("")
def list_friends(user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.list_friends(user, db)


@router.delete("/{friend_id}")
def delete_friend(friend_id: str, user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.delete_friend(user, friend_id, db)
