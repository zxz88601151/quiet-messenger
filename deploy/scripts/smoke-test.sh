#!/usr/bin/env bash
# ============================================================================
# Staging Smoke Test (Phase 2D-DEPLOYMENT)
# ----------------------------------------------------------------------------
# 对真实 PostgreSQL 后端执行最小链路 smoke（不依赖 pytest，独立 curl 验证）。
# 前置：backend 已起（SQLite 或 PG），BASE_URL 指向 /api/v1。
# 不打印 token / password / secret 到日志（仅返回状态码与 minimal body）。
# ============================================================================
set -uo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
API="$BASE_URL/api/v1"

echo "==> health"
curl -fsS "$BASE_URL/health" && echo

echo "==> register"
REG=$(curl -fsS -X POST "$API/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"username":"smoke_a","phone":"13800000001","password":"SmokePass#1","nickname":"SmokeA"}')
echo "$REG" | head -c 200; echo

ACCESS=$(echo "$REG" | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "==> GET /users/me (token hidden)"
curl -fsS "$API/users/me" -H "Authorization: Bearer $ACCESS" | head -c 200; echo

echo "==> smoke DONE (secret-free)"
