#!/usr/bin/env bash
# 数据备份:PG 全量 dump + 本地文件数据(知识库文档/上传图片)
# 建议 crontab: 0 3 * * * /path/to/deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
BACKUP_DIR="${BACKUP_DIR:-./backups}"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

echo "📦 备份数据库..."
docker compose exec -T pg pg_dump -U agentplatform agentplatform | gzip > "$BACKUP_DIR/db-$STAMP.sql.gz"

echo "📁 备份本地文件数据(kb 文档/上传图片)..."
tar -czf "$BACKUP_DIR/files-$STAMP.tar.gz -C "$HOME/.agentplatform" kb uploads 2>/dev/null || echo "   (无本地文件数据,跳过)"

# 保留最近 14 份
ls -t "$BACKUP_DIR"/db-*.sql.gz | tail -n +15 | xargs rm -f 2>/dev/null || true
ls -t "$BACKUP_DIR"/files-*.tar.gz | tail -n +15 | xargs rm -f 2>/dev/null || true
echo "✅ 备份完成: $BACKUP_DIR (db-$STAMP.sql.gz)"
