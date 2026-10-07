# 极简私人通讯 — 部署说明 (Phase 2D-DEPLOYMENT)

本目录仅包含 **Staging 部署基础设施**，不涉及任何业务功能。业务代码在 `../backend/`。

## 目录结构

```
deploy/
  nginx/
    nginx.conf        # HTTPS 反代：80→443 跳转，/api/ 与 /health → backend:8000
    certs/            # 证书存放（fullchain.pem + privkey.pem）；不提交真实证书
  scripts/
    gen-selfsigned-cert.sh  # 本地自签证书（仅本地验证，非生产）
    smoke-test.sh           # 最小链路 smoke（health + register + me）
  README.md
docker-compose.yml    # postgres(internal) + backend(internal:8000) + nginx(443)
backend/
  Dockerfile          # 非 root 运行；启动先 alembic upgrade head 再 uvicorn
  docker-entrypoint.sh
  .env.example        # 环境变量模板（复制为 .env，禁止提交 .env）
```

## 安全约定（强制）

- **禁止硬编码 secret**：JWT_SECRET / 数据库密码 / 任何密钥只经 `.env` 或部署环境注入，不进源码、Dockerfile、compose、Git。
- **数据库不暴露公网**：`postgres` 服务不映射端口，仅 compose 内部网络可达。
- **Backend 不直接暴露公网**：仅 `nginx` 暴露 443；backend 内部端口 8000 只被 nginx 访问。
- **CORS 环境变量驱动**：`CORS_ORIGINS` 明确来源，禁止 `"*"` 通配。
- **日志不输出 secret**：应用层已排除 password / token / password_hash；部署脚本不 echo secret。
- **HTTPS 优先**：HTTP 80 仅做 301 跳转；真实域名用正式 CA 证书替换 `certs/`。

## 快速开始（有 Docker 的环境）

```bash
# 1. 准备环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入强随机 JWT_SECRET 与数据库密码

# 2.（可选）本地自签证书用于验证
bash deploy/scripts/gen-selfsigned-cert.sh

# 3. 启动
docker compose up -d

# 4. 健康检查
curl -fsS https://localhost/health   # 经 Nginx HTTPS
curl -fsS http://127.0.0.1:8000/health  # 后端直连（仅内部）

# 5. smoke test
bash deploy/scripts/smoke-test.sh https://localhost
```

## 无 Docker 的本机验证（Windows 本机）

本阶段在 Windows 本机安装 PostgreSQL（非超级用户业务库 `chat_staging`），直接运行 backend
（uvicorn）连真实 PG，实跑 Alembic + 全链路 smoke（见 PHASE2D_DEPLOYMENT_REPORT）。
Docker / Nginx 实跑在本环境标记为 `BLOCKED BY ENVIRONMENT`，但上述产物已静态就绪。

## 禁止范围（Phase 2D-DEPLOYMENT）

不新增：WebSocket / QR / E2EE / Handoff / Space / 群聊 / 消息高级功能 / Privacy UI /
Flutter / PySide6 / 新 REST API / 修改契约。仅做部署就绪验证。
