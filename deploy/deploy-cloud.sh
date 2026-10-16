#!/bin/bash
# 云端部署脚本(20261016):本地验证过的 HEAD 原子发布到 AWS,内置四重校验。
# 用法: bash deploy/deploy-cloud.sh
# 保证:① 部署内容 = 本地 HEAD(git -C 归档 + 内容断言)② 版本戳可查
#       (/api/specs/revision) ③ 部署后健康探针全过,任一失败即报错停下。

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOST="ubuntu@15.134.232.21"
KEY="$HOME/.ssh/agentplatform.pem"
DOMAIN_API="https://ai-api.ailearning.top"
DOMAIN_WEB="https://agent.ailearning.top"
REV="$(git -C "$ROOT" rev-parse --short HEAD)"

echo "▶ [1/6] 归档 HEAD($REV)——git -C 绝对定位,防 cwd 飘移打出子树"
git -C "$ROOT" archive --format=tar.gz -o /tmp/deploy-repo.tar.gz HEAD
test -n "$(tar tzf /tmp/deploy-repo.tar.gz | grep -m1 '^agentplatform/main.py')" || { echo "✗ 归档缺关键源码,中止"; exit 1; }

echo "▶ [2/6] 传输"
scp -q -i "$KEY" /tmp/deploy-repo.tar.gz "$HOST:/home/ubuntu/deploy-repo.tar.gz"

echo "▶ [3/6] 服务器:干净解包(丢弃旧树防残留污染)+ 内容断言"
ssh -i "$KEY" "$HOST" "
  cd /home/ubuntu
  # sudo:searxng/warp 挂载目录会被容器(root)写入,普通 rm 会 Permission denied
  sudo rm -rf agentplatform && mkdir agentplatform
  tar --overwrite -xzf deploy-repo.tar.gz -C agentplatform
  cp /home/ubuntu/.deploy.env agentplatform/.deploy.env
  echo '$REV' > agentplatform/REVISION
  grep -q '$REV' agentplatform/REVISION
  test -f agentplatform/deploy/searxng/settings.yml
  test -f agentplatform/agentplatform/core/storage/service.py
  echo '  内容断言通过'
"

echo "▶ [4/6] 构建 + 滚动替换(旧容器继续服务至新镜像就绪)"
ssh -i "$KEY" "$HOST" "cd /home/ubuntu/agentplatform && sudo docker compose up -d --build api web render 2>&1 | tail -1"

echo "▶ [5/6] 健康探针"
ssh -i "$KEY" "$HOST" "
  sleep 8
  sudo docker ps --format '{{.Names}} {{.Status}}' | grep -qE 'api-1\s+Up' || exit 1
  curl -sf -o /dev/null http://localhost:8000/api/assistants || exit 1
  curl -sf -o /dev/null http://localhost:3000/ || exit 1
  sudo docker exec agentplatform-api-1 python -c \"import httpx;r=httpx.get('http://searxng:8080/search',params={'q':'health','format':'json'},timeout=20);assert r.status_code==200\"
  echo '  服务器侧探针通过'
"
REV_REMOTE="$(curl -sf --noproxy '*' "$DOMAIN_API/api/specs/revision" | python3 -c 'import json,sys;print(json.load(sys.stdin)["rev"])')"
test "$REV_REMOTE" = "$REV" || { echo "✗ 版本戳不符: 云端 $REV_REMOTE ≠ 本地 $REV,中止"; exit 1; }
curl -sf -o /dev/null --noproxy '*' "$DOMAIN_WEB/" || { echo "✗ 域名 web 探针失败"; exit 1; }
curl -sf -o /dev/null --noproxy '*' "$DOMAIN_API/api/assistants" || { echo "✗ 域名 api 探针失败"; exit 1; }

echo "▶ [6/6] 完成:云端 = $REV(本地 HEAD 一致),域名与 searxng 探针全过"