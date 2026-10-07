"""社交数据面业务逻辑（Phase 2C）。

覆盖：好友请求 / 接受 / 拒绝 / 好友列表 / 删除好友 / 会话列表 / 会话详情 /
消息分页 / 发消息。严格服从 API_CONTRACT §2/§3/§4 与 STATE_MACHINES。

关键规则（不自行扩大）：
- 接受好友 → 双向 Friendship + 预创建规范化 Conversation（user_a=min, user_b=max）。
- 删除好友 → 移除双向 Friendship，保留 Message；后续发消息校验 Friendship 缺失 → 403。
- 发消息 → 前置校验双方为好友 + 是会话一方，否则 403。
- 消息幂等 → 相同 (conversation_id, client_message_id) 返回已存消息（非新建）。
- Message 无服务端 status 字段（仅 client_message_id + read_at）。
- 已读回执 / typing 中继 / WS 推送属 Phase 5，本 Phase 不实现（仅 REST 数据面）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import (
    conflict,
    conversation_forbidden,
    duplicate_request,
    friend_not_found,
    friend_required,
    not_found,
    validation_error,
)
from app.models.conversation import Conversation, Message
from app.models.friend import FriendRequest, Friendship
from app.models.user import User
from app.schemas.social import (
    AcceptResult,
    ConversationPublic,
    FriendPublic,
    FriendRequestPublic,
    MessagePage,
    MessagePublic,
    UserSearchItem,
)
from app.schemas.user import PrivacySettings, to_user_public
from app.services.connection_manager import manager, make_event


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_summary(user: User) -> UserSearchItem:
    return UserSearchItem(
        id=str(user.id),
        username=user.username,
        nickname=user.nickname,
        avatar=user.avatar,
    )


# ---------------- User ----------------
def get_me(user: User) -> dict:
    """GET /users/me：返回完整 User + privacy_settings（5 键）。"""
    return to_user_public(user).model_dump(mode="json")


def patch_me(user: User, data: dict, db: Session) -> dict:
    """PATCH /users/me：merge patch nickname/avatar/bio + privacy_settings。

    - username / phone 不可改（契约 §2：V1 默认忽略并提示不可改）。
    - privacy_settings 仅更新提交的键，未提交保持不变（merge patch）。
    """
    if "nickname" in data and data["nickname"] is not None:
        user.nickname = data["nickname"]
    if "avatar" in data:
        user.avatar = data["avatar"]
    if "bio" in data:
        user.bio = data["bio"]

    ps = user.privacy_settings or {}
    if data.get("privacy_settings") is not None:
        incoming = data["privacy_settings"]
        merged = dict(ps)
        for k, v in incoming.items():
            if k == "online_status_visibility":
                merged[k] = v  # 已通过 schema 校验取值
            elif k == "message_retention":
                merged[k] = v
            else:
                merged[k] = v
        # 兜底：确保 5 键完整
        complete = PrivacySettings(**merged).model_dump()
        user.privacy_settings = complete

    db.commit()
    db.refresh(user)
    return to_user_public(user).model_dump(mode="json")


def search_users(q: str, db: Session, limit: int = 20) -> list[dict]:
    """GET /users/search?q=：username/phone 模糊搜索。

    phone 仅匹配精确或后缀（契约 §2：避免泄露）。
    """
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    stmt = (
        select(User)
        .where((User.username.ilike(like)) | (User.phone.like(f"{q[-6:]}%") if q.isdigit() else User.phone.ilike(like)))
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    # 二次过滤：phone 数字查询仅返回精确或后缀匹配结果
    result = []
    for u in rows:
        if q.isdigit():
            if u.phone == q or u.phone.endswith(q):
                result.append(_user_summary(u).model_dump(mode="json"))
        else:
            result.append(_user_summary(u).model_dump(mode="json"))
    return result


# ---------------- Friend ----------------
def _resolve_target(db: Session, target: str) -> User | None:
    return db.execute(
        select(User).where((User.username == target) | (User.phone == target))
    ).scalar_one_or_none()


async def create_friend_request(sender: User, target: str, db: Session) -> dict:
    """POST /friends/requests：发送好友请求。

    - 自加自己 → 400。
    - 已是好友（反向 accepted）→ 返回既有友谊（200 已存在）。
    - 已存在 pending/accepted（同方向）→ 返回既有请求（200 已存在）。
    """
    target = (target or "").strip()
    if not target:
        raise validation_error("target_username_or_phone 不能为空")
    if target == sender.username or target == sender.phone:
        raise validation_error("不能添加自己为好友")
    tuser = _resolve_target(db, target)
    if tuser is None:
        raise not_found("目标用户不存在")

    # 反向已是好友？
    existing_friend = db.execute(
        select(Friendship).where(
            Friendship.user_id == sender.id, Friendship.friend_id == tuser.id
        )
    ).scalar_one_or_none()
    if existing_friend is not None:
        # 视为已是好友，返回友谊（200 已存在）
        conv = _ensure_conversation(db, sender.id, tuser.id)
        return {
            "friendship": FriendPublic.from_db(tuser, existing_friend.created_at).model_dump(mode="json"),
            "conversation": ConversationPublic.from_db(conv, peer=tuser).model_dump(mode="json"),
        }

    # 同方向已存在 pending/accepted？
    dup = db.execute(
        select(FriendRequest).where(
            FriendRequest.sender_id == sender.id,
            FriendRequest.receiver_id == tuser.id,
            FriendRequest.status.in_(["pending", "accepted"]),
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise duplicate_request("该好友请求已存在")
    # 同方向已存在 rejected？→ 重新激活（避免唯一约束冲突导致 500）
    rejected = db.execute(
        select(FriendRequest).where(
            FriendRequest.sender_id == sender.id,
            FriendRequest.receiver_id == tuser.id,
            FriendRequest.status == "rejected",
        )
    ).scalar_one_or_none()
    if rejected is not None:
        rejected.status = "pending"
        rejected.updated_at = _now()
        db.commit()
        db.refresh(rejected)
        return FriendRequestPublic.from_db(rejected, sender=sender, receiver=tuser).model_dump(mode="json")
    # 反向 pending（对方已向你发过请求）→ 视为已存在，返回该请求
    rev = db.execute(
        select(FriendRequest).where(
            FriendRequest.sender_id == tuser.id,
            FriendRequest.receiver_id == sender.id,
            FriendRequest.status == "pending",
        )
    ).scalar_one_or_none()
    if rev is not None:
        raise duplicate_request("对方已向你发送好友请求")

    req = FriendRequest(sender_id=sender.id, receiver_id=tuser.id, status="pending")
    db.add(req)
    db.commit()
    db.refresh(req)
    result = FriendRequestPublic.from_db(req, sender=sender, receiver=tuser).model_dump(mode="json")
    # WS realtime push: notify receiver of new incoming friend request.
    # DB commit has already succeeded; WS push failure must not affect the
    # persisted request (REST is source of truth, client can reconcile).
    try:
        await manager.send_to_user(str(tuser.id), make_event("friend.request.created", result))
    except Exception:
        pass
    return result


def list_friend_requests(user: User, req_type: str, db: Session) -> list[dict]:
    """GET /friends/requests?type=incoming|outgoing|all。"""
    if req_type == "incoming":
        stmt = select(FriendRequest).where(FriendRequest.receiver_id == user.id)
    elif req_type == "outgoing":
        stmt = select(FriendRequest).where(FriendRequest.sender_id == user.id)
    else:
        stmt = select(FriendRequest).where(
            (FriendRequest.sender_id == user.id) | (FriendRequest.receiver_id == user.id)
        )
    rows = db.execute(stmt.order_by(FriendRequest.created_at.desc())).scalars().all()
    out = []
    for r in rows:
        sender = db.execute(select(User).where(User.id == r.sender_id)).scalar_one_or_none()
        receiver = db.execute(select(User).where(User.id == r.receiver_id)).scalar_one_or_none()
        out.append(FriendRequestPublic.from_db(r, sender=sender, receiver=receiver).model_dump(mode="json"))
    return out


def _get_request_or_404(db: Session, request_id: str, user: User) -> FriendRequest:
    try:
        rid = uuid.UUID(request_id)
    except (ValueError, TypeError):
        raise friend_not_found()
    req = db.execute(select(FriendRequest).where(FriendRequest.id == rid)).scalar_one_or_none()
    if req is None:
        raise friend_not_found()
    # 仅接收方可 accept/reject
    if req.receiver_id != user.id:
        raise friend_not_found("仅接收方可操作该请求")
    return req


def accept_friend_request(user: User, request_id: str, db: Session) -> dict:
    """POST /friends/requests/{id}/accept：建立双向 Friendship + 预创建 Conversation。"""
    req = _get_request_or_404(db, request_id, user)
    if req.status != "pending":
        raise conflict("该请求已处理")

    sender = db.execute(select(User).where(User.id == req.sender_id)).scalar_one_or_none()
    if sender is None:
        raise friend_not_found("发送方不存在")

    # 双向 Friendship（UNIQUE 防重）
    _add_friendship(db, user.id, req.sender_id)
    _add_friendship(db, req.sender_id, user.id)

    req.status = "accepted"
    req.updated_at = _now()
    db.commit()

    conv = _ensure_conversation(db, user.id, req.sender_id)
    friendship = FriendPublic.from_db(sender, created_at=_now()).model_dump(mode="json")
    # created_at 以 Friendship 实际写入时间为准
    frow = db.execute(
        select(Friendship).where(Friendship.user_id == user.id, Friendship.friend_id == req.sender_id)
    ).scalar_one_or_none()
    if frow is not None:
        friendship["friendship_created_at"] = frow.created_at
    conv_out = ConversationPublic.from_db(conv, peer=sender).model_dump(mode="json")
    return AcceptResult(friendship=friendship, conversation=conv_out).model_dump(mode="json")


def reject_friend_request(user: User, request_id: str, db: Session) -> dict:
    """POST /friends/requests/{id}/reject：status → rejected（终态不可逆）。"""
    req = _get_request_or_404(db, request_id, user)
    if req.status != "pending":
        raise conflict("该请求已处理")
    req.status = "rejected"
    req.updated_at = _now()
    db.commit()
    return {"ok": True}


def _add_friendship(db: Session, uid: uuid.UUID, fid: uuid.UUID) -> None:
    exists = db.execute(
        select(Friendship).where(Friendship.user_id == uid, Friendship.friend_id == fid)
    ).scalar_one_or_none()
    if exists is None:
        db.add(Friendship(user_id=uid, friend_id=fid))


def list_friends(user: User, db: Session) -> list[dict]:
    """GET /friends：好友列表（含 friendship_created_at）。"""
    rows = db.execute(
        select(Friendship).where(Friendship.user_id == user.id)
    ).scalars().all()
    out = []
    for f in rows:
        fu = db.execute(select(User).where(User.id == f.friend_id)).scalar_one_or_none()
        if fu is None:
            continue
        out.append(FriendPublic.from_db(fu, created_at=f.created_at).model_dump(mode="json"))
    return out


def delete_friend(user: User, friend_id: str, db: Session) -> dict:
    """DELETE /friends/{friend_id}：移除双向 Friendship，保留 Message。"""
    try:
        fid = uuid.UUID(friend_id)
    except (ValueError, TypeError):
        raise friend_not_found("好友不存在")
    fu = db.execute(select(User).where(User.id == fid)).scalar_one_or_none()
    if fu is None:
        raise friend_not_found("好友不存在")
    f1 = db.execute(
        select(Friendship).where(Friendship.user_id == user.id, Friendship.friend_id == fid)
    ).scalar_one_or_none()
    if f1 is None:
        raise friend_not_found("好友关系不存在")
    f2 = db.execute(
        select(Friendship).where(Friendship.user_id == fid, Friendship.friend_id == user.id)
    ).scalar_one_or_none()
    for f in (f1, f2):
        if f is not None:
            db.delete(f)
    db.commit()
    return {"ok": True}


# ---------------- Conversation / Message ----------------
def _ensure_conversation(db: Session, uid1: uuid.UUID, uid2: uuid.UUID) -> Conversation:
    """规范化 Conversation（user_a=min, user_b=max），存在则返回。"""
    a, b = (uid1, uid2) if uid1 < uid2 else (uid2, uid1)
    conv = db.execute(
        select(Conversation).where(Conversation.user_a == a, Conversation.user_b == b)
    ).scalar_one_or_none()
    if conv is None:
        conv = Conversation(user_a=a, user_b=b)
        db.add(conv)
        db.commit()
        db.refresh(conv)
    return conv


def _is_friend(db: Session, uid1: uuid.UUID, uid2: uuid.UUID) -> bool:
    return db.execute(
        select(Friendship).where(Friendship.user_id == uid1, Friendship.friend_id == uid2)
    ).scalar_one_or_none() is not None


def list_conversations(user: User, db: Session) -> list[dict]:
    """GET /conversations：按 updated_at 倒序，含 peer / last_message / unread_count。"""
    convs = db.execute(
        select(Conversation)
        .where((Conversation.user_a == user.id) | (Conversation.user_b == user.id))
        .order_by(Conversation.updated_at.desc())
    ).scalars().all()
    out = []
    for conv in convs:
        peer_id = conv.user_b if conv.user_a == user.id else conv.user_a
        peer = db.execute(select(User).where(User.id == peer_id)).scalar_one_or_none()
        last = db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        unread = db.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id == conv.id,
                Message.sender_id != user.id,
                Message.read_at.is_(None),
            )
        ).scalar_one()
        out.append(
            ConversationPublic.from_db(
                conv, peer=peer, last_message=last, unread_count=int(unread or 0)
            ).model_dump(mode="json")
        )
    return out


def get_conversation(user: User, conversation_id: str, db: Session) -> dict:
    """GET /conversations/{id}：越权 → 403。"""
    conv = _load_conversation(db, conversation_id)
    if conv is None:
        raise not_found("会话不存在")
    if not (conv.user_a == user.id or conv.user_b == user.id):
        raise conversation_forbidden()
    peer_id = conv.user_b if conv.user_a == user.id else conv.user_a
    peer = db.execute(select(User).where(User.id == peer_id)).scalar_one_or_none()
    return ConversationPublic.from_db(conv, peer=peer).model_dump(mode="json")


def _load_conversation(db: Session, conversation_id: str) -> Conversation | None:
    try:
        cid = uuid.UUID(conversation_id)
    except (ValueError, TypeError):
        return None
    return db.execute(select(Conversation).where(Conversation.id == cid)).scalar_one_or_none()


def list_messages(user: User, conversation_id: str, cursor: str, limit: int, db: Session) -> dict:
    """GET /conversations/{id}/messages?cursor=&limit=：游标分页，created_at 升序。

    cursor 编码为 "{created_at_iso}|{message_id}"（复合游标），避免同一时刻多消息
    用纯 created_at 比较时丢消息。
    """
    conv = _load_conversation(db, conversation_id)
    if conv is None:
        raise not_found("会话不存在")
    if not (conv.user_a == user.id or conv.user_b == user.id):
        raise conversation_forbidden()

    limit = max(1, min(limit or 50, 100))
    stmt = select(Message).where(Message.conversation_id == conv.id)
    if cursor:
        parts = cursor.split("|", 1)
        if len(parts) != 2:
            raise validation_error("cursor 格式无效")
        cur_dt_raw, cur_id = parts
        try:
            cur_dt = datetime.fromisoformat(cur_dt_raw.replace("Z", "+00:00"))
        except ValueError:
            raise validation_error("cursor 格式无效")
        try:
            cur_uuid = uuid.UUID(cur_id)
        except (ValueError, TypeError):
            raise validation_error("cursor 格式无效")
        # 复合条件：(created_at, id) > (cur_dt, cur_uuid)
        stmt = stmt.where(
            (Message.created_at > cur_dt)
            | ((Message.created_at == cur_dt) & (Message.id > cur_uuid))
        )
    rows = db.execute(
        stmt.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit + 1)
    ).scalars().all()

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = ""
    if has_more and page:
        last = page[-1]
        next_cursor = f"{last.created_at.isoformat()}|{last.id}" if last.created_at else ""
    items = [MessagePublic.from_db(m).model_dump(mode="json") for m in page]
    return MessagePage(items=items, next_cursor=next_cursor).model_dump(mode="json")


async def send_message(user: User, conversation_id: str, content: str, client_message_id: str, db: Session) -> dict:
    """POST /conversations/{id}/messages：好友前置校验 + 会话成员校验 + 幂等 + WS 广播。

    前置：双方为好友 + 是会话一方，否则 403。
    去重：相同 (conversation_id, client_message_id) 返回已存消息（不再广播，防重复 event）。
    WS 广播：仅发给会话对方（peer），不发给发送者自身——发送者由 REST response 显示，
    避免 REST + WS 双重显示（授权§八）。
    """
    conv = _load_conversation(db, conversation_id)
    if conv is None:
        raise not_found("会话不存在")
    if not (conv.user_a == user.id or conv.user_b == user.id):
        raise conversation_forbidden()

    peer_id = conv.user_b if conv.user_a == user.id else conv.user_a
    if not _is_friend(db, user.id, peer_id):
        raise friend_required("双方必须为好友关系")

    # 幂等：相同 (conversation_id, client_message_id)
    existing = db.execute(
        select(Message).where(
            Message.conversation_id == conv.id, Message.client_message_id == client_message_id
        )
    ).scalar_one_or_none()
    if existing is not None:
        return MessagePublic.from_db(existing).model_dump(mode="json")

    msg = Message(
        conversation_id=conv.id,
        sender_id=user.id,
        client_message_id=client_message_id,
        content=content,
        created_at=_now(),  # 显式微秒精度，避免同秒批量插入时间戳碰撞导致分页丢消息
    )
    db.add(msg)
    conv.updated_at = _now()
    db.commit()
    db.refresh(msg)

    # WS 实时广播给会话对方（Peer），不广播发送者自身（REST response 已覆盖发送端）。
    # 失败不应影响消息持久化（DB 是 Source of Truth，授权§九）。
    try:
        payload = MessagePublic.from_db(msg).model_dump(mode="json")
        await manager.send_to_user(str(peer_id), make_event("message.created", payload))
    except Exception:
        # WS 广播失败：消息已在 DB，客户端重新进入会话可经 REST 恢复。
        pass

    return MessagePublic.from_db(msg).model_dump(mode="json")
