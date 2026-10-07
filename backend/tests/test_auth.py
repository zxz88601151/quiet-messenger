"""V1.1 Phase 2B Auth 测试。

覆盖：register / login / refresh / logout / forgot / reset / device。
安全：密码不明文、无用户枚举、token 校验、轮换、吊销。
"""
from __future__ import annotations

import pytest


# ---------------- Register ----------------
def test_register_ok(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "phone": "13800000001", "password": "secret123", "nickname": "Alice"},
    )
    assert r.status_code == 201
    b = r.json()
    assert "access_token" in b and "refresh_token" in b
    assert b["user"]["username"] == "alice"
    assert b["user"]["phone"] == "13800000001"
    assert "password_hash" not in b["user"]
    assert b["device"]["device_type"] == "mobile"


def test_register_duplicate(client):
    payload = {"username": "dup", "phone": "13700000003", "password": "secret123", "nickname": "Dup"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    # 重复 username
    r2 = client.post("/api/v1/auth/register", json={**payload, "phone": "13700000004"})
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DUPLICATE_USER"
    # 重复 phone
    r3 = client.post("/api/v1/auth/register", json={**payload, "username": "dup2"})
    assert r3.status_code == 409


def test_register_invalid(client):
    # 空白用户名
    assert client.post("/api/v1/auth/register", json={"username": "  ", "phone": "13700000005", "password": "secret123", "nickname": "X"}).status_code == 400
    # 短密码
    assert client.post("/api/v1/auth/register", json={"username": "shortpw", "phone": "13700000006", "password": "123", "nickname": "X"}).status_code == 400
    # 非数字 phone
    assert client.post("/api/v1/auth/register", json={"username": "badphone", "phone": "abc", "password": "secret123", "nickname": "X"}).status_code == 400
    # 缺字段（契约：所有校验错误统一 400 VALIDATION_ERROR，见 API_CONTRACT §7）
    assert client.post("/api/v1/auth/register", json={"username": "miss", "phone": "13700000007"}).status_code == 400


def test_password_not_plaintext(client):
    r = client.post("/api/v1/auth/register", json={"username": "seccheck", "phone": "13700000008", "password": "secret123", "nickname": "Sec"})
    assert r.status_code == 201
    # 响应里不应有 password / password_hash
    assert "password" not in r.json()["user"]
    assert "password_hash" not in r.json()["user"]


# ---------------- Login ----------------
def test_login_ok(client):
    client.post("/api/v1/auth/register", json={"username": "loginuser", "phone": "13700000009", "password": "secret123", "nickname": "LU"})
    r = client.post("/api/v1/auth/login", json={"identifier": "loginuser", "password": "secret123", "device": {"device_type": "mobile", "device_name": "P", "device_identifier": "dev-l"}})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_wrong_password(client):
    client.post("/api/v1/auth/register", json={"username": "wp", "phone": "13700000010", "password": "secret123", "nickname": "WP"})
    r = client.post("/api/v1/auth/login", json={"identifier": "wp", "password": "WRONG", "device": {"device_type": "mobile"}})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_nonexistent_no_enum(client):
    # 不存在账号不应暴露"用户不存在"，统一 401 INVALID_CREDENTIALS
    r = client.post("/api/v1/auth/login", json={"identifier": "nope_user", "password": "whatever", "device": {"device_type": "mobile"}})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_phone_identifier(client):
    client.post("/api/v1/auth/register", json={"username": "byphone", "phone": "13700000011", "password": "secret123", "nickname": "BP"})
    r = client.post("/api/v1/auth/login", json={"identifier": "13700000011", "password": "secret123", "device": {"device_type": "mobile"}})
    assert r.status_code == 200


# ---------------- Refresh（轮换）----------------
def test_refresh_ok(client, auth_headers):
    creds = auth_headers()
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": creds["refresh_token"]})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body and "refresh_token" in body
    # 新 access token 必须可真实用于受保护端点（防止 refresh 返回错误 token 的回归）
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_refresh_revoked_reuse_old(client, auth_headers):
    creds = auth_headers()
    old = creds["refresh_token"]
    # 轮换一次，旧令牌应失效
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r.status_code == 200
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 401


def test_refresh_invalid_token(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage.token.value"})
    assert r.status_code == 401


def test_refresh_wrong_type(client, auth_headers):
    creds = auth_headers()
    # access token 当 refresh 用 → 401
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": creds["access_token"]})
    assert r.status_code == 401


# ---------------- Logout ----------------
def test_logout_ok(client, auth_headers):
    creds = auth_headers()
    r = client.post("/api/v1/auth/logout", json={"refresh_token": creds["refresh_token"]})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_logout_repeat(client, auth_headers):
    creds = auth_headers()
    client.post("/api/v1/auth/logout", json={"refresh_token": creds["refresh_token"]})
    r2 = client.post("/api/v1/auth/logout", json={"refresh_token": creds["refresh_token"]})
    # 重复 logout：token 已吊销，应 401（幂等安全）
    assert r2.status_code == 401


def test_logout_then_refresh_fail(client, auth_headers):
    creds = auth_headers()
    client.post("/api/v1/auth/logout", json={"refresh_token": creds["refresh_token"]})
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": creds["refresh_token"]})
    assert r.status_code == 401


# ---------------- Forgot / Reset ----------------
def test_forgot_ok_returns_dev_code(client):
    client.post("/api/v1/auth/register", json={"username": "forgotu", "phone": "13700000012", "password": "secret123", "nickname": "F"})
    r = client.post("/api/v1/auth/forgot-password", json={"phone": "13700000012"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "dev_code" in r.json()  # dev 环境返回


def test_forgot_nonexist_no_enum(client):
    r = client.post("/api/v1/auth/forgot-password", json={"phone": "00000000000"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "dev_code" not in r.json()  # 不存在账号不返回 code，不泄露存在性


def test_reset_ok(client):
    client.post("/api/v1/auth/register", json={"username": "resetu", "phone": "13700000013", "password": "oldpass1", "nickname": "R"})
    code_r = client.post("/api/v1/auth/forgot-password", json={"phone": "13700000013"})
    code = code_r.json()["dev_code"]
    r = client.post("/api/v1/auth/reset-password", json={"phone": "13700000013", "code": code, "new_password": "newpass2"})
    assert r.status_code == 200 and r.json()["ok"] is True
    # 新密码可登录
    login = client.post("/api/v1/auth/login", json={"identifier": "resetu", "password": "newpass2", "device": {"device_type": "mobile"}})
    assert login.status_code == 200


def test_reset_wrong_code(client):
    client.post("/api/v1/auth/register", json={"username": "resetc", "phone": "13700000014", "password": "oldpass1", "nickname": "RC"})
    r = client.post("/api/v1/auth/reset-password", json={"phone": "13700000014", "code": "000000", "new_password": "newpass2"})
    assert r.status_code == 400


def test_reset_reuse_code(client):
    client.post("/api/v1/auth/register", json={"username": "resetr", "phone": "13700000015", "password": "oldpass1", "nickname": "RR"})
    code = client.post("/api/v1/auth/forgot-password", json={"phone": "13700000015"}).json()["dev_code"]
    assert client.post("/api/v1/auth/reset-password", json={"phone": "13700000015", "code": code, "new_password": "newpass2"}).status_code == 200
    # 重复使用同一 code 应失败（单次使用）
    r2 = client.post("/api/v1/auth/reset-password", json={"phone": "13700000015", "code": code, "new_password": "another3"})
    assert r2.status_code == 400


# ---------------- Device ----------------
def test_device_binding_on_register(client):
    r = client.post("/api/v1/auth/register", json={"username": "devbind", "phone": "13700000016", "password": "secret123", "nickname": "D"})
    assert r.json()["device"]["device_type"] == "mobile"


def test_multi_device(client):
    # 同一用户登录两个不同 device_identifier
    reg = client.post("/api/v1/auth/register", json={"username": "multidev", "phone": "13700000017", "password": "secret123", "nickname": "M"})
    uid = reg.json()["user"]["id"]
    l1 = client.post("/api/v1/auth/login", json={"identifier": "multidev", "password": "secret123", "device": {"device_type": "mobile", "device_identifier": "dev-A"}})
    l2 = client.post("/api/v1/auth/login", json={"identifier": "multidev", "password": "secret123", "device": {"device_type": "desktop", "device_identifier": "dev-B"}})
    assert l1.status_code == 200 and l2.status_code == 200
    assert l1.json()["device"]["id"] != l2.json()["device"]["id"]


def test_same_device_relogin_no_duplicate(client):
    client.post("/api/v1/auth/register", json={"username": "samedev", "phone": "13700000018", "password": "secret123", "nickname": "S"})
    a = client.post("/api/v1/auth/login", json={"identifier": "samedev", "password": "secret123", "device": {"device_type": "mobile", "device_identifier": "same-id"}})
    b = client.post("/api/v1/auth/login", json={"identifier": "samedev", "password": "secret123", "device": {"device_type": "mobile", "device_identifier": "same-id"}})
    assert a.json()["device"]["id"] == b.json()["device"]["id"]


def test_login_after_logout_reactivates_device(client):
    """回归测试：登出后设备被 revoked，重新登录应重新激活而非新建（避免唯一约束冲突）。"""
    reg = client.post("/api/v1/auth/register", json={"username": "relogin", "phone": "13700000019", "password": "secret123", "nickname": "R", "device": {"device_type": "mobile", "device_identifier": "phone-001"}})
    assert reg.status_code == 201
    device_id = reg.json()["device"]["id"]
    refresh_token = reg.json()["refresh_token"]

    # 登出：device 被 revoked
    lo = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert lo.status_code == 200

    # 重新登录同一 device_identifier：应重新激活 revoked 设备，而非失败
    relogin = client.post("/api/v1/auth/login", json={"identifier": "relogin", "password": "secret123", "device": {"device_type": "mobile", "device_identifier": "phone-001"}})
    assert relogin.status_code == 200, f"重新登录失败: {relogin.status_code} {relogin.text}"
    # 设备应被重新激活（同一 device_id）
    assert relogin.json()["device"]["id"] == device_id
    assert relogin.json()["device"]["revoked_at"] is None


def test_invalid_device_type(client):
    r = client.post("/api/v1/auth/login", json={"identifier": "x", "password": "y", "device": {"device_type": "watch"}})
    assert r.status_code == 400
