# syntax=docker/dockerfile:1
# agentplatform 后端镜像:uv 同步依赖 + uvicorn 运行
# build context = 仓库根(含 pyproject.toml / uv.lock / migrations / alembic.ini)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_HTTP_TIMEOUT=300

# 国内网络可加速(构建时传入): docker compose build --build-arg UV_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ARG UV_INDEX=

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# 先拷贝依赖清单与源码(利用层缓存)
COPY pyproject.toml uv.lock ./
COPY agentplatform ./agentplatform
COPY migrations ./migrations
COPY alembic.ini ./
# wheels/(可选,本地构建提速):预下载的 linux aarch64 轮子,存在则离线装配,
# 构建容器零网络依赖(20260930 colima VM 大文件传输极慢的绕行方案)。
# 目录为空或缺失时回落网络安装。wheels/ 已 gitignore,不入库。
COPY wheels* ./wheels/

# 仅运行时依赖(不带 dev 组)。
# wheels 可用 → uv venv + 离线 uv pip(与 uv.lock 同源导出的 requirements);
# 否则 → 网络 uv sync(原路径)
RUN if ls /app/wheels/*.whl > /dev/null 2>&1; then \
        uv export --frozen --no-dev --no-emit-project --format requirements-txt -o /tmp/req.txt && \
        uv venv /app/.venv && \
        uv pip install --python /app/.venv/bin/python --offline \
            --find-links /app/wheels -r /tmp/req.txt; \
    else \
        UV_DEFAULT_INDEX=${UV_INDEX:+$UV_INDEX} uv sync --frozen --no-dev || uv sync --frozen --no-dev; \
    fi

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "agentplatform.main:app", "--host", "0.0.0.0", "--port", "8000"]
