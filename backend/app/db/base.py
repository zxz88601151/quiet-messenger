"""SQLAlchemy engine / session / metadata 基础。

Phase 2A：建立引擎与 session 工厂；连接池参数对 PostgreSQL 友好，
SQLite 下自动降级（check_same_thread=False）。
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# SQLite 需要 check_same_thread=False 才能在 FastAPI 多线程下使用。
_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """所有 ORM Model 的声明基类。metadata 是 Alembic 迁移的唯一事实源。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级 DB session。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
