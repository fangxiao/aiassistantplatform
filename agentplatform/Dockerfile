# syntax=docker/dockerfile:1
# agentplatform 后端镜像:uv 同步依赖 + uvicorn 运行
# build context = 仓库根(含 pyproject.toml / uv.lock / migrations / alembic.ini)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python3.12

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# 先拷贝依赖清单与源码(利用层缓存)
COPY pyproject.toml uv.lock ./
COPY agentplatform ./agentplatform
COPY migrations ./migrations
COPY alembic.ini ./

# 仅运行时依赖(不带 dev 组)
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "agentplatform.main:app", "--host", "0.0.0.0", "--port", "8000"]
