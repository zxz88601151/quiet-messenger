"""Auth 业务逻辑（Phase 2B）。

集中实现 register / login / refresh / logout / forgot-password / reset-password
以及 Device 绑定、RefreshToken 轮换与吊销。

严格服从 API_CONTRACT §1 + DATA_MODEL。
- 密码 bcrypt；库只存 password_hash。
- 不泄露用户存在性（forgot-password 统一响应）。
- reset code 为 Dev Mock（生产接短信），具备生命周期 + 单次使用
  + 连续失败作废（S-2 纵深）。
- 重置密码后吊销该用户全部 refresh token 与设备会话（S-1 修复）。
- refresh token 轮换带 family 追踪与复用检测（H-1 修复）。
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    duplicate_user,
    invalid_credentials,
    unauthorized,
    validation_error,
)
from app.core.security import (
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token_record,
    get_live_family_token,
    hash_password,
    revoke_refresh_token,
    revoke_token_family,
    verify_password,
    verify_refresh_token_with_status,
)
from app.models.device import Device
from app.models.login_audit import LoginAuditLog
from app.models.token import RefreshToken
from app.models.user import User
from app.schemas.auth import DeviceInput
from app.schemas.user import to_device_public, to_user_public


# S-2 纵深：同一 phone 针对当前 code 连续输错超过此次数，直接作废 code。
# 与路由层限流配合：限流防"广撒网"爆破，此计数防针对单号的慢速试错。
MAX_RESET_CODE_ATTEMPTS = 10
# H-1：已吊销 token 在宽限期内重放且确为轮换链上的重试 → 视为合法重试；
# 超过宽限或 device 已吊销（logout 路径）→ 视为盗用，熔断整个 family。
REUSE_GRACE_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_audit_log(
    db: Session,
    *,
    user_id: uuid.UUID | None,
    identifier: str,
    action: str,
    failure_reason: str | None = None,
    device_in: DeviceInput | None = None,
    device_type: str | None = None,
    device_name: str | None = None,
    device_identifier: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """写入登录审计日志。失败安全：日志写入异常不影响主流程。"""
    try:
        log = LoginAuditLog(
            user_id=user_id,
            identifier=identifier,
            action=action,
            failure_reason=failure_reason,
            device_type=device_in.device_type if device_in else device_type,
            device_name=device_in.device_name if device_in else device_name,
            device_identifier=device_in.device_identifier if device_in else device_identifier,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log)
        db.commit()
    except Exception:
        # 审计日志写入失败不影响登录主流程
        db.rollback()


# --- Dev Mock 重置码存储（生产替换为短信服务）---
class _ResetCodeStore:
    """phone -> { code, expires_at, used }。内存存储，仅 Dev 演示用。"""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._failures: dict[str, int] = {}  # phone -> 针对当前 code 的连续失败次数

    def issue(self, phone: str, ttl_seconds: int = 600) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._store[phone] = {
            "code": code,
            "expires_at": _now() + timedelta(seconds=ttl_seconds),
            "used": False,
        }
        self._failures.pop(phone, None)  # 新码签发，失败计数清零
        return code

    def verify(self, phone: str, code: str) -> bool:
        rec = self._store.get(phone)
        if rec is None or rec["used"]:
            return False
        if rec["expires_at"] < _now():
            return False
        if secrets.compare_digest(rec["code"], code):
            rec["used"] = True
            self._failures.pop(phone, None)
            return True
        # S-2 纵深：连续失败超限则直接作废当前 code，攻击者无法对同一个
        # code 无限试错（需重新走 forgot-password 拿新码）。
        fails = self._failures.get(phone, 0) + 1
        self._failures[phone] = fails
        if fails >= MAX_RESET_CODE_ATTEMPTS:
            rec["used"] = True
        return False


reset_code_store = _ResetCodeStore()


# ---------------- Device 绑定 ----------------
def _bind_or_get_device(
    db: Session, user: User, device_in: DeviceInput | None
) -> Device:
    """注册/登录时绑定设备。

    - 有 device_identifier：复用已有未吊销设备（同一用户同标识），否则新建。
    - 无 device（register 缺省）：自动建默认 mobile 设备。
    - FIX: 若同标识设备已被吊销（登出导致 revoked_at），重新激活而非新建，
      否则会违反 (user_id, device_identifier) 唯一约束导致登录失败。
    """
    if device_in is None:
        device_in = DeviceInput(device_type="mobile", device_name="My Phone")
    if device_in.device_identifier:
        existing = db.execute(
            select(Device).where(
                Device.user_id == user.id,
                Device.device_identifier == device_in.device_identifier,
                Device.revoked_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.device_type = device_in.device_type
            existing.device_name = device_in.device_name
            existing.last_active_at = _now()
            db.commit()
            db.refresh(existing)
            return existing
        # 同标识设备已被吊销（登出），重新激活
        revoked = db.execute(
            select(Device).where(
                Device.user_id == user.id,
                Device.device_identifier == device_in.device_identifier,
                Device.revoked_at.is_not(None),
            )
        ).scalar_one_or_none()
        if revoked is not None:
            revoked.revoked_at = None
            revoked.device_type = device_in.device_type
            revoked.device_name = device_in.device_name
            revoked.last_active_at = _now()
            db.commit()
            db.refresh(revoked)
            return revoked
    dev = Device(
        user_id=user.id,
        device_type=device_in.device_type,
        device_name=device_in.device_name,
        device_identifier=device_in.device_identifier,
        last_active_at=_now(),
    )
    db.add(dev)
    db.commit()
    db.refresh(dev)
    return dev


def _issue_tokens(user: User, device: Device) -> tuple[str, str]:
    access = create_access_token(str(user.id), str(device.id))
    raw_refresh, _ = create_refresh_token_record(str(user.id), str(device.id))
    return access, raw_refresh


# ---------------- Register ----------------
def register(db: Session, data) -> tuple[User, Device, str, str]:
    # 重复账号检查（username / phone 任一存在即冲突）
    dup = db.execute(
        select(User).where(
            (User.username == data.username) | (User.phone == data.phone)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise duplicate_user()

    user = User(
        username=data.username,
        phone=data.phone,
        password_hash=hash_password(data.password),
        nickname=data.nickname,
        privacy_settings={
            "read_receipt_enabled": True,
            "online_status_visibility": "all",
            "typing_indicator_enabled": True,
            "new_device_login_alert": True,
            "message_retention": "forever",
        },
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    device = _bind_or_get_device(db, user, data.device)
    access, raw_refresh = _issue_tokens(user, device)
    return user, device, access, raw_refresh


# ---------------- Login ----------------
def login(
    db: Session,
    data,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, Device, str, str] | None:
    # 按 username 或 phone 查找（统一查找，不区分以防水枚举）
    user = db.execute(
        select(User).where(
            (User.username == data.identifier) | (User.phone == data.identifier)
        )
    ).scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        # 统一返回 INVALID_CREDENTIALS，不暴露账号是否存在
        reason = "user_not_found" if user is None else "invalid_password"
        _write_audit_log(
            db,
            user_id=user.id if user else None,
            identifier=data.identifier,
            action="login_failure",
            failure_reason=reason,
            device_in=data.device,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise invalid_credentials()
    device = _bind_or_get_device(db, user, data.device)
    access, raw_refresh = _issue_tokens(user, device)
    _write_audit_log(
        db,
        user_id=user.id,
        identifier=data.identifier,
        action="login_success",
        device_in=data.device,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return user, device, access, raw_refresh


# ---------------- Refresh（轮换 + H-1 复用检测）----------------
def refresh(raw_token: str) -> tuple[User, Device, str, str]:
    from app.db.base import SessionLocal
    from app.core.security import _revoke_by_hash

    rec, status = verify_refresh_token_with_status(raw_token)
    if rec is None or status in ("not_found", "expired"):
        raise unauthorized("Refresh Token 无效、已过期或被吊销")

    if status == "valid":
        # 正常轮换：按哈希吊销旧 token（记 revoked_at），新 token 继承 family
        with SessionLocal() as db:
            db_rec = db.execute(
                select(RefreshToken).where(RefreshToken.id == rec.id)
            ).scalar_one_or_none()
            if db_rec is None:
                raise unauthorized("Refresh Token 无效")
            _revoke_by_hash(db, db_rec.token_hash)
            family_id = db_rec.family_id or uuid.uuid4()
            user = db.execute(select(User).where(User.id == db_rec.user_id)).scalar_one_or_none()
            device = db.execute(select(Device).where(Device.id == db_rec.device_id)).scalar_one_or_none()
            if user is None or device is None:
                db.commit()
                raise unauthorized("用户或设备不存在")
            access = create_access_token(str(user.id), str(device.id))
            new_raw, _ = create_refresh_token_record(
                str(user.id), str(device.id), family_id=family_id
            )
            db.commit()
            return user, device, access, new_raw

    # ---- H-1：已吊销 token 再次出现 → 复用检测 ----
    with SessionLocal() as db:
        db_rec = db.execute(
            select(RefreshToken).where(RefreshToken.id == rec.id)
        ).scalar_one_or_none()
        if db_rec is None:
            raise unauthorized("Refresh Token 无效")
        family_id = db_rec.family_id
        device = db.execute(
            select(Device).where(Device.id == db_rec.device_id)
        ).scalar_one_or_none()
        # logout / 设备吊销路径：设备已 revoked → 无宽限，直接熔断
        device_revoked = device is not None and device.revoked_at is not None
        within_grace = (
            db_rec.revoked_at is not None
            and (_now() - db_rec.revoked_at.replace(tzinfo=timezone.utc)).total_seconds()
            <= REUSE_GRACE_SECONDS
        )
        live = get_live_family_token(db, family_id) if family_id else None
        if not device_revoked and within_grace and live is not None:
            # 宽限内的轮换重试（如客户端超时重发）：视为合法重试，
            # 用 family 内最新 live token 的身份重新签发一次
            _revoke_by_hash(db, live.token_hash)
            new_family = live.family_id or uuid.uuid4()
            user = db.execute(select(User).where(User.id == live.user_id)).scalar_one_or_none()
            dev = db.execute(select(Device).where(Device.id == live.device_id)).scalar_one_or_none()
            if user is None or dev is None:
                db.commit()
                raise unauthorized("用户或设备不存在")
            access = create_access_token(str(user.id), str(dev.id))
            new_raw, _ = create_refresh_token_record(
                str(user.id), str(dev.id), family_id=new_family
            )
            db.commit()
            return user, dev, access, new_raw
        # 否则视为盗用：熔断整个 family 并记审计
        if family_id is not None:
            revoke_token_family(db, family_id)
        _write_audit_log(
            db,
            user_id=db_rec.user_id,
            identifier=str(db_rec.user_id),
            action="refresh_token_reuse_detected",
            failure_reason="revoked_token_reused",
        )
        db.commit()
        raise unauthorized("检测到 Refresh Token 复用，已吊销该设备全部会话，请重新登录")


# ---------------- Logout ----------------
def logout(
    raw_token: str,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    from app.db.base import SessionLocal
    from app.core.security import hash_token, verify_refresh_token
    from app.models.token import RefreshToken

    # 先校验 token 仍有效；已吊销/不存在 → 401（重复 logout 幂等安全）。
    rec = verify_refresh_token(raw_token)
    if rec is None:
        raise unauthorized("Refresh Token 已失效或已登出")
    revoke_refresh_token(raw_token)
    # Device 撤销：按 refresh token 找到 device 并置 revoked_at
    with SessionLocal() as db:
        dev = db.execute(
            select(Device).where(Device.id == rec.device_id)
        ).scalar_one_or_none()
        if dev is not None and dev.revoked_at is None:
            dev.revoked_at = _now()
            db.commit()
        # 写入登出审计日志
        _write_audit_log(
            db,
            user_id=rec.user_id,
            identifier=str(rec.user_id),
            action="logout",
            device_type=dev.device_type if dev else None,
            device_name=dev.device_name if dev else None,
            device_identifier=dev.device_identifier if dev else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )


# ---------------- Forgot / Reset ----------------
def revoke_all_user_sessions(db: Session, user: User) -> None:
    """S-1：吊销该用户全部 refresh token 与全部设备会话。

    改密场景通常意味着凭证可能已失陷：必须让所有已签发的 refresh token
    即时失效，并作废全部设备信任；否则攻击者可凭旧 refresh token
    继续签发 access token，改密形同虚设。
    注意：commit 由调用方统一完成（含 password_hash 更新），保证原子性。
    """
    now = _now()
    tokens = (
        db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)
            )
        )
        .scalars()
        .all()
    )
    for tok in tokens:
        tok.revoked = True
        tok.revoked_at = now
    devices = (
        db.execute(
            select(Device).where(
                Device.user_id == user.id, Device.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for dev in devices:
        dev.revoked_at = now


def forgot_password(db: Session, phone: str, dev_mode: bool) -> tuple[bool, str | None]:
    # 不泄露用户是否存在：无论账号是否存在都返回 ok=true。
    # Dev 模式：若存在账号才签发 dev_code（仅用于演示；生产接短信）。
    user = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    dev_code = None
    if user is not None and dev_mode:
        dev_code = reset_code_store.issue(phone)
    return True, dev_code


def reset_password(
    db: Session, phone: str, code: str, new_password: str
) -> tuple[bool, str | None]:
    """重置密码。成功时同时吊销该用户全部设备会话（S-1 修复）。

    返回 (ok, user_id)：user_id 供路由层做 WS 收尾（断开该用户全部 live 连接）。
    """
    user = db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
    if user is None:
        # 统一响应 ok=false（不泄露账号是否存在）；这里由路由决定返回 200/400
        return False, None
    if not reset_code_store.verify(phone, code):
        return False, None
    user.password_hash = hash_password(new_password)
    # S-1：改密即吊销全部会话（refresh token + 设备），与 password_hash
    # 更新同一 commit 落库，保证原子性。
    revoke_all_user_sessions(db, user)
    db.commit()
    return True, str(user.id)
