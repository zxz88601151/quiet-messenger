#!/usr/bin/env sh
# ============================================================================
# Backend 容器启动入口 (Phase 2D-DEPLOYMENT)
# ----------------------------------------------------------------------------
# 1) 执行 Alembic migration（真实 PostgreSQL）。失败即退出（容器明显失败）。
# 2) 启动 uvicorn。注意：日志中不输出 secret（应用层已做排除）。
# 不在脚本中 echo 任何-secret 变量。
# ============================================================================
set -e

echo "[entrypoint] running database migration (alembic upgrade head)..."
alembic upgrade head
echo "[entrypoint] migration done."

echo "[entrypoint] starting uvicorn on 0.0.0.0:8000 (internal only)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
