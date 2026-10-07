#!/usr/bin/env bash
# ============================================================================
# Staging PostgreSQL 初始化（Phase 2D-DEPLOYMENT）
# ----------------------------------------------------------------------------
# 创建专用 Staging 数据库与业务用户（非超级用户）。
# 禁止：使用超级用户运行业务；连接 Production 数据库；硬编码密码到脚本/Git。
# 密码通过环境变量 STAGING_PG_PASSWORD 注入（或交互输入）。
# PG 默认超级用户：postgres（仅在初始化阶段使用一次）。
# ============================================================================
set -euo pipefail

PG_BIN="${PG_BIN:-/c/Program Files/PostgreSQL/17/bin}"
PATH="$PG_BIN:$PATH"

DB="${STAGING_PG_DB:-chat_staging}"
USER="${STAGING_PG_USER:-chat_staging_user}"

if [[ -z "${STAGING_PG_PASSWORD:-}" ]]; then
  read -rs -p "Enter password for $USER: " STAGING_PG_PASSWORD
  echo
fi

echo "[pg] 初始化 Staging 数据库与用户 (非超级用户)..."
psql -U postgres -h 127.0.0.1 -p 5432 -v ON_ERROR_STOP=1 <<SQL
-- 业务用户（非超级用户）
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${USER}') THEN
    CREATE ROLE ${USER} LOGIN PASSWORD '${STAGING_PG_PASSWORD}' NOSUPERUSER INHERIT CREATEDB;
  END IF;
END
\$\$;

-- 专用数据库，属主为业务用户
SELECT 'CREATE DATABASE ${DB} OWNER ${USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB}')\gexec
SQL

echo "[pg] DONE: db=$DB user=$USER (密码经环境变量注入，未写盘)"
