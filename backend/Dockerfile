# ============================================================================
# 极简私人通讯 — Backend Dockerfile (Phase 2D-DEPLOYMENT)
# ----------------------------------------------------------------------------
# 仅部署基础设施，不新增任何业务功能。
# 安全约定：
#   - 不硬编码 JWT_SECRET / 数据库密码 / 任何 secret（均由环境变量注入）。
#   - 非 root 用户运行（uid 10001）。
#   - 启动先执行 alembic upgrade head，失败则容器以非 0 退出（明显失败）。
#   - 不向 stdout/stderr 打印 secret（应用层已排除；下方 ENV 仅透传配置名）。
#   - 仅暴露内部端口 8000；由 Nginx 反向代理，不直接暴露公网业务端口。
# ============================================================================
FROM python:3.13-slim

# 避免缓冲导致日志丢失；关闭 pyc 写入减小镜像
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# 系统依赖（psycopg 二进制驱动已含，无需系统 libpq；如改用源码版需 libpq-dev）
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（利用层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（运行时不需要 tests；测试在 CI 独立执行，见 §14）
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

# 非 root 运行
RUN groupadd -g 10001 appgroup && useradd -u 10001 -g appgroup -m appuser \
    && chown -R appuser:appgroup ${APP_HOME}
USER appuser

# 健康检查：仅探测 /health，不依赖外部；失败时容器不健康
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
