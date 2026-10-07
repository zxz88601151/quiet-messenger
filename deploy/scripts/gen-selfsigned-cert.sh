#!/usr/bin/env bash
# ============================================================================
# 本地自签证书生成（仅用于无真实域名时的本地 HTTPS 验证）
# ----------------------------------------------------------------------------
# ⚠️ 自签证书不被公网浏览器信任，仅用于 Staging 本地链路验证。
#    真实域名可用时应改为 Let's Encrypt / 正式 CA 证书，并替换 certs/ 下文件。
#    本阶段若无法获得真实域名，HTTPS 验证标记为 BLOCKED BY ENVIRONMENT。
# ============================================================================
set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")/../nginx/certs" && pwd)"
mkdir -p "$CERT_DIR"
KEY="$CERT_DIR/privkey.pem"
CRT="$CERT_DIR/fullchain.pem"

if [[ -f "$KEY" && -f "$CRT" ]]; then
  echo "[cert] 已存在证书，跳过生成: $CERT_DIR"
  exit 0
fi

echo "[cert] 生成自签证书 (CN=localhost) ..."
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$KEY" -out "$CRT" -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

echo "[cert] 已生成:"
echo "  $KEY"
echo "  $CRT"
echo "[cert] ⚠️ 自签证书仅本地验证用，不用于生产/真实域名。"
