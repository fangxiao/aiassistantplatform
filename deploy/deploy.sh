#!/usr/bin/env bash
# AgentPlatform 一键部署(单机):pg + redis + api + web(+ 可选搜索栈)
# 用法: ./deploy/deploy.sh [--with-search]
# 详见 deploy/README.md
set -euo pipefail
cd "$(dirname "$0")/.."

echo "🚀 AgentPlatform 部署开始..."

# 1. 生成部署密钥(已设则沿用)
if [ -z "${SECRET_KEY:-}" ] && [ ! -f .deploy.env ]; then
  echo "SECRET_KEY=$(openssl rand -hex 32)" > .deploy.env
  echo "✅ 已生成 SECRET_KEY(.deploy.env,请妥善保管/纳入备份)"
fi
[ -f .deploy.env ] && set -a && . ./.deploy.env && set +a

# 2. 局域网提示(NEXT_PUBLIC_API_BASE 决定其他设备能否访问)
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
export NEXT_PUBLIC_API_BASE="${NEXT_PUBLIC_API_BASE:-http://${LAN_IP}:8000/api}"
echo "🌐 前端 API 地址: ${NEXT_PUBLIC_API_BASE}(手机/其他电脑访问需用此 IP;如不符请 export NEXT_PUBLIC_API_BASE 后重跑)"

# 3. 构建并启动核心四件套
docker compose up -d --build
echo "⏳ 等待数据库健康..."
sleep 12

# 4. 数据库迁移(容器内执行)
echo "📦 执行数据库迁移..."
docker compose exec -T api alembic upgrade head

# 5. 可选:联网搜索栈(SearXNG + WARP,免费无额度)
if [ "${1:-}" = "--with-search" ]; then
  echo "🔍 启动联网搜索栈(SearXNG + Cloudflare WARP)..."
  docker compose -f deploy/docker-compose.search.yml up -d
  echo "   记得在 api 环境加: WEB_SEARCH_PROVIDER=searxng SEARXNG_BASE_URL=http://searxng:8080"
fi

echo ""
echo "🎉 部署完成!"
echo "   Web:  http://localhost:3000 (局域网: http://${LAN_IP}:3000)"
echo "   API:  http://localhost:8000/docs"
echo "   数据备份: ./deploy/backup.sh"
echo "   日志:   docker compose logs -f api"
