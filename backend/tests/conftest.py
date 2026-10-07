"""pytest fixtures（Phase 2A + 2B）。

- 注入 dev JWT_SECRET（仅测试，不硬编码到源码/生产配置）
- 使用独立测试库（系统临时目录 + 唯一文件名），避免污染开发库
- 提供 TestClient 与鉴权 helper
"""
import os
import sys
import tempfile
from pathlib import Path

# 必须在导入 app 前设置环境变量（config 在导入时读取）。
BACKEND_ROOT = Path(__file__).resolve().parent.parent

# 测试库放到系统临时目录，并使用唯一文件名。
# 原因：本沙箱对 os.remove 做了 safe-delete 包装，SQLite 文件无法被直接删除
# （windows-sandbox-recycle-bin-unavailable → 抛 OSError）。改用唯一临时路径，
# 每次运行自动生成新库，避免任何删除操作，彻底规避该限制。
_TEST_DB_NAME = f"chat_test_{os.getpid()}.db"
_TEST_DB_PATH = Path(tempfile.gettempdir()) / _TEST_DB_NAME
_DATABASE_URL = f"sqlite:///{_TEST_DB_PATH.as_posix()}"

os.environ["ENVIRONMENT"] = "development"
os.environ["JWT_SECRET"] = "dev-test-secret-32bytes-minimum-length!!"
os.environ["DATABASE_URL"] = _DATABASE_URL

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    """测试前用 alembic upgrade head 重建测试库（不使用 os.remove，规避沙箱 safe-delete）。"""
    from alembic import command
    from alembic.config import Config

    # 保证迁移使用同一 DATABASE_URL：alembic env 读 os.environ["DATABASE_URL"]。
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield
    # 注：不在此删除测试库（沙箱禁止 os.remove）；唯一文件名保证不会污染下次运行。


@pytest.fixture(autouse=True)
def _clean_db():
    """每个测试前清空所有表，保证用例间相互独立（不依赖 os.remove，规避沙箱 safe-delete）。"""
    from app.db.base import Base, SessionLocal
    from sqlalchemy import text

    with SessionLocal() as db:
        # 关闭外键约束后按 metadata 顺序 DELETE 全部表（SQLite 不支持 TRUNCATE）。
        db.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(text(f"DELETE FROM {table.name}"))
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.commit()
    yield


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """返回注册并登录一个用户、给出 Bearer 头的 helper。"""

    def _make(username="bob", phone="13900000002", password="secret123"):
        r = client.post(
            "/api/v1/auth/register",
            json={
                "username": username,
                "phone": phone,
                "password": password,
                "nickname": username.title(),
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        return {
            "access_token": body["access_token"],
            "refresh_token": body["refresh_token"],
            "user_id": body["user"]["id"],
            "device_id": body["device"]["id"],
            "password": password,
        }

    return _make
