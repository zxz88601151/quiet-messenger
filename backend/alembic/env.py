"""Alembic env — 接入 app Base.metadata 与运行时配置。

数据库 URL 来自 app.config.get_settings().DATABASE_URL（环境变量优先），
不硬编码到 alembic.ini，保证开发(SQLite)/生产(PostgreSQL) 通过 DATABASE_URL 切换。
"""
from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config, pool
from alembic import context

# 让 app 包可导入（alembic 在 backend/ 下运行）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
import app.models  # noqa: E402,F401  # 确保全部 Model 注册到 metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用运行时配置覆盖 sqlalchemy.url，避免 alembic.ini 硬编码。
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
