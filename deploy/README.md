# 部署指南

单机部署 AgentPlatform(给公司/个人使用)。整套 **零付费** 可跑(含联网搜索)。

## 〇、给新公司快速开台

见 [NEW-COMPANY.md](./NEW-COMPANY.md)——30 分钟部署+配模型+初始化管理员。

## 一、准备

- Docker(含 compose)
- 端口:3000(Web)/ 8000(API)/ 5432(PG)/ 6379(Redis)
- 可选:域名(HTTPS 用)

## 二、一键部署

```bash
git clone <仓库> && cd agentplatform
./deploy/deploy.sh            # 核心四件套:pg + redis + api + web
./deploy/deploy.sh --with-search   # 附加联网搜索栈(SearXNG + WARP,免费无额度)
```

脚本会:生成 SECRET_KEY → 构建镜像 → 启动 → 数据库迁移 → 打印访问地址。

**局域网访问**:脚本自动探测本机 IP 并注入 `NEXT_PUBLIC_API_BASE`,
手机/其他电脑用打印出来的局域网地址访问;如不符,`export NEXT_PUBLIC_API_BASE=http://<本机IP>:8000/api` 后重跑。

**国内网络加速构建**(可选):

```bash
docker compose build --build-arg UV_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
```

## 三、LLM 与服务配置

api 容器环境变量(compose `environment` 段或 `.deploy.env`):

| 变量 | 说明 |
|---|---|
| `SECRET_KEY` | 部署密钥(脚本自动生成;**务必换离默认值**) |
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `DEFAULT_MODEL` | LLM 网关(OpenAI 兼容) |
| `MULTIMODAL_MODEL` | 看图模型 |
| `KB_EMBEDDING_MODEL` + embedding 端点 | 知识库向量化(管理台配置亦可) |
| `WEB_SEARCH_PROVIDER=searxng` + `SEARXNG_BASE_URL` | 联网搜索(配合 --with-search) |
| `ACTION_HTTP_ALLOWLIST=["a.com","b.com"]` | agent 动作白名单(空=禁用) |
| `BROWSER_DEV_ROUTE_ANY` | 保持 false(生产) |

## 四、HTTPS(对外提供时)

Caddy 模板自动申请证书:

```bash
# brew install caddy && 改 deploy/Caddyfile 的域名
caddy run --config deploy/Caddyfile
```

同域反代后前端 API 地址改 `https://<域名>/api`。

## 五、数据备份

```bash
./deploy/backup.sh            # PG dump + 本地文件数据,保留最近 14 份
# crontab 每日 3 点:
# 0 3 * * * /path/to/deploy/backup.sh
```

恢复:`gunzip -c db-xxx.sql.gz | docker compose exec -T pg psql -U agentplatform agentplatform`

## 六、常用运维

```bash
docker compose logs -f api            # 后端日志
docker compose exec api alembic upgrade head   # 升级后迁移
docker compose pull && docker compose up -d --build   # 更新版本
docker compose exec pg psql -U agentplatform       # 进数据库
```

## 已知限制

- 调度器与浏览器隧道为进程内单例:请保持 api 单副本(`--workers 1` 默认);
  多副本会重复触发定时任务(靠运行锁去重,不致错但浪费)
- 对话图片存本地卷(~/.agentplatform/uploads 经 backup.sh 备份);多机部署需共享存储或对象存储化
