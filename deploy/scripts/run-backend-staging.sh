#!/usr/bin/env bash
# ============================================================================
# 本机 (非 Docker) Staging 后端启动 (Phase 2D-DEPLOYMENT)
# ----------------------------------------------------------------------------
# 直接以 uvicorn 连真实 PostgreSQL 运行后端，用于无 Docker 环境下的实跑验证。
# 环境变量从 backend/.env 读取（不提交 Git）。
# 启动前先 alembic upgrade head（真实 PG migration）。
# 日志不输出 secret（应用层已排除；脚本不 echo secret）。
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")/../../backend"

if [[ ! -f .env ]]; then
  echo "ERROR: backend/.env 不存在。请 cp .env.example .env 并填入真实值。" >&2
  exit 1
fi

echo "[run] loading backend/.env ..."
set -a
source ./.env
set +a

echo "[run] alembic upgrade head (real PostgreSQL)..."
alembic upgrade head

echo "[run] starting uvicorn on 127.0.0.1:8000 (internal, behind nginx)..."
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
