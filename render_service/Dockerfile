# html_render sidecar(T18.17):Playwright + Chromium + python-pptx
# 镜像较大(~1.2GB,浏览器内置)——独立于主 API 镜像,可独立扩缩
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /srv
COPY render_service.py .
RUN pip install --no-cache-dir fastapi uvicorn python-pptx playwright

EXPOSE 8001
CMD ["uvicorn", "render_service:app", "--host", "0.0.0.0", "--port", "8001"]
