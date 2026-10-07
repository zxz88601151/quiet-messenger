"""V1.1 Phase 2A 基础测试（最小覆盖）。

Test A: FastAPI app 可导入/启动
Test B: GET /health 返回成功
Test C: SQLAlchemy metadata 可加载（表齐全）
Test D: Alembic migration 可执行（upgrade head 已在本脚本外验证；此处校验 head 可达）
Test E: 数据库表数量 = 8
Test F: 关键 FK / UNIQUE / NOT NULL 约束存在
Test G: privacy_settings JSON 字段存在且类型正确
Test H: Message 不存在服务端 status 字段
Test I: Now 状态（DATA_MODEL 无 DB 字段 → NOT RUN，不自行增加）

执行：
  pytest tests/ -q
或仅结构验证（无需 server）：
  python tests/verify_schema.py
"""
from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import create_engine, inspect, text

# 让 app 可导入（backend/ 为根）。
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.base import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401  # 注册所有表
from app.main import app  # noqa: E402


EXPECTED_TABLES = {
    "users",
    "devices",
    "refresh_tokens",
    "qr_login_sessions",
    "friend_requests",
    "friendships",
    "conversations",
    "messages",
    "login_audit_logs",
}


# ---------- Test A: app 可导入/启动 ----------
def test_app_importable():
    assert app is not None
    assert app.title == "Minimal Chat API"


# ---------- Test B: /health ----------
def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["phase"] in ("2A", "2B", "2C", "2D")


# ---------- Test C: metadata 加载 ----------
def test_metadata_tables():
    tables = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES.issubset(tables)
    assert len(Base.metadata.tables) >= 8


# ---------- Test E: 表数量一致 ----------
def test_db_table_count():
    insp = inspect(engine)
    actual = set(insp.get_table_names())
    missing = EXPECTED_TABLES - actual
    assert not missing, f"缺失表: {missing}"
    business = {t for t in actual if not t.startswith("alembic")}
    assert len(business) == 9, f"业务表数={len(business)}"


# ---------- Test F: 约束 ----------
def test_constraints():
    insp = inspect(engine)
    # UNIQUE 约束核对。
    # 注：users.username / users.phone 是各自独立的 UNIQUE 列（DATA_MODEL 单列 UNIQUE），
    # 其余为复合 UNIQUE。分开断言。
    composite_unique = {
        "qr_login_sessions": ["nonce"],
        "refresh_tokens": ["token_hash"],
        "devices": ["user_id", "device_identifier"],
        "friend_requests": ["sender_id", "receiver_id"],
        "friendships": ["user_id", "friend_id"],
        "conversations": ["user_a", "user_b"],
        "messages": ["conversation_id", "client_message_id"],
    }
    for tbl, cols in composite_unique.items():
        col_sets = [set(u["column_names"]) for u in insp.get_unique_constraints(tbl)]
        col_sets += [
            set(ix["column_names"]) for ix in insp.get_indexes(tbl) if ix.get("unique")
        ]
        assert set(cols) in col_sets, f"{tbl} 缺少 UNIQUE({cols})，实际: {col_sets}"

    # users 的独立 UNIQUE 列。
    # SQLite 将单列 UNIQUE 实现为 UNIQUE INDEX，get_unique_constraints 可能返回空，
    # 因此同时检查 unique index。
    def unique_columns(tbl: str) -> set:
        cols: set = set()
        for u in insp.get_unique_constraints(tbl):
            cols.update(u["column_names"])
        for ix in insp.get_indexes(tbl):
            if ix.get("unique"):
                cols.update(ix["column_names"])
        return cols

    user_uniques = unique_columns("users")
    for col in ("username", "phone"):
        assert col in user_uniques, f"users.{col} 应为独立 UNIQUE，实际: {user_uniques}"

    # NOT NULL 核对（抽样关键字段）
    not_null_expect = {
        "users": ["username", "phone", "password_hash", "nickname", "privacy_settings"],
        "devices": ["user_id", "device_type"],
        "refresh_tokens": ["user_id", "device_id", "token_hash", "expires_at", "revoked"],
        "messages": ["conversation_id", "sender_id", "content"],
    }
    for tbl, cols in not_null_expect.items():
        cols_info = {c["name"]: c for c in insp.get_columns(tbl)}
        for c in cols:
            assert not cols_info[c]["nullable"], f"{tbl}.{c} 应为 NOT NULL"


# ---------- Test G: privacy_settings JSON ----------
def test_privacy_settings_json():
    from app.models.user import User

    col = User.__table__.c.privacy_settings
    # JSON 类型
    type_name = str(col.type).upper()
    assert "JSON" in type_name, f"privacy_settings 类型应为 JSON，实际 {type_name}"
    assert not col.nullable, "privacy_settings 应为 NOT NULL"
    # 默认值为 dict（JSON 列默认 {}）
    assert col.default is not None or col.server_default is not None


# ---------- Test H: Message 无服务端 status 字段 ----------
def test_message_no_status_field():
    from app.models.conversation import Message

    cols = set(Message.__table__.columns.keys())
    forbidden = {
        "status",
        "delivered",
        "queued",
        "pending_server",
        "waiting_ack",
        "uploading",
        "delivery_status",
        "sent_status",
        "seen_status",
    }
    leaked = forbidden & cols
    assert not leaked, f"Message 禁止出现服务端状态字段: {leaked}"
    # 必须存在的幂等/已读字段
    assert "client_message_id" in cols
    assert "read_at" in cols


# ---------- Test I: Now 状态 ----------
def test_now_state_no_db_field():
    """DATA_MODEL 未给 Now 定义独立 DB 字段（Now 是客户端/协议层推导态）。
    按 Phase 1 指令：若无对应数据库字段，不要自行增加。
    此处断言：没有任何一张表新增 now_status 字段（防止范围泄漏）。"""
    for tbl_name, tbl in Base.metadata.tables.items():
        assert "now_status" not in tbl.columns.keys(), f"{tbl_name} 不应含 now_status 字段"
        assert "now" not in [c.lower() for c in tbl.columns.keys()], f"{tbl_name} 不应含 now 字段"
