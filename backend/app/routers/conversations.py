"""Conversation / Message 路由（Phase 2C，API_CONTRACT §4）。

GET /conversations / GET /conversations/{id} / messages（分页） / POST messages。
严格不实现：WebSocket 实时推送（message.created / message.read / typing，属 Phase 5）。
发消息前置：双方好友 + 会话成员，否则 403；client_message_id 幂等。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.social import MessageCreate
from app.services import social_service

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.get("")
def list_conversations(user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.list_conversations(user, db)


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, user: User = Depends(get_current_user), db=Depends(get_db)):
    return social_service.get_conversation(user, conversation_id, db)


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: str,
    cursor: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return social_service.list_messages(user, conversation_id, cursor, limit, db)


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def send_message(
    conversation_id: str,
    data: MessageCreate,
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    return await social_service.send_message(user, conversation_id, data.content, data.client_message_id, db)
