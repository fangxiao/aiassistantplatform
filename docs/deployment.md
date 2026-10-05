# AgentPlatform 部署与运维指南

本指南详细说明 AgentPlatform 智能体平台在本地开发与生产环境中的完整部署流程。

---

## 1. 架构总览与组件依赖

平台由以下核心服务组成：
1. **API 网关与核心后端** (`agentplatform`): 基于 Python 3.12 + FastAPI + SQLAlchemy 构建，提供 REST API、SSE 消息流式分发、Agent 运行时与注册表。
2. **Web 前端工作台** (`web`): 基于 Next.js 14 + Tailwind CSS 构建，提供交互式对话工作台、助手广场与开发者中心。
3. **关系型数据库** (`PostgreSQL 16`): 持久化存储用户、插件清单、注册表技能工具、会话消息信封与审计事件。
4. **高速缓存** (`Redis 7`): 缓存活跃会话上下文与会话锁。

---

## 2. 环境变量配置

请参考根目录 `.env.example` 创建运行时的 `.env` 文件：

```bash
# 后端配置
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/agentplatform
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-secure-fernet-compatible-secret-key-32-chars-or-more
CORS_ORIGINS=["http://localhost:3000"]
PORT=8000
# ⚠ SECRET_KEY 写在项目根 .env(compose environment 段插值来源),
#   写 .deploy.env 无效(env_file 会被 environment 覆盖)

# 前端配置 (web/.env.local)
NEXT_PUBLIC_API_BASE=http://localhost:8000/api
```

### 认证相关(M24,设计 018;公网部署时按需开启)

```bash
# OAuth 回调与邮件链接的公网基址(不配则 OAuth 回调指回 localhost)
PUBLIC_API_BASE=https://ai-api.ailearning.top
PUBLIC_WEB_BASE=https://ai-web.ailearning.top     # 邮箱验证链接目标(M24 P2)

# GitHub 联登(P1):github.com → Settings → Developer settings → OAuth Apps 建 App 后填入
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# 邮箱验证邮件投递(M24 P2,复用通知 SMTP;不配则注册后跳过发信)
NOTIFY_SMTP_HOST=
NOTIFY_SMTP_PORT=465
NOTIFY_SMTP_USER=
NOTIFY_SMTP_PASS=

# 飞书扫码登录(M24 P2):复用机器人 FEISHU_APP_ID/SECRET;
# 另需在飞书开放平台「安全设置 → 重定向 URL 白名单」登记:
#   https://ai-api.ailearning.top/api/auth/feishu/callback
# 本地调试另加 http://localhost:8000/api/auth/feishu/callback
```

登录会话为双令牌(M24 P2):access JWT 2h(Bearer)+ refresh 30d(httpOnly Cookie,
`Path=/api/auth`,自动轮换,重放即吊销整族);CLI 用 PAT,不受影响。

### SECRET_KEY 轮换(20261006 已执行一次,程序留档)

默认密钥公网暴露 = 任何人可伪造 admin JWT。轮换步骤(注意顺序):

1. **先重加密存量密文**(llm_endpoints.api_key_enc / feishu_bots.app_secret_enc,
   Fernet 密钥派生自 SECRET_KEY):在旧容器内用旧密钥解密 → 新密钥重加密(一次性脚本)
2. 新 SECRET_KEY 写**项目根 `.env`**(不是 .deploy.env)→ `docker compose up -d`
3. 验证:旧 JWT 401 / 新登录 200 / 端点解密正常 / 飞书机器人重连
4. 影响:JWT/签名 URL 全部失效(重登录即可);**PAT 不受影响**(sha256 落库)

---

## 3. 本地快速启动 (开发模式)

### 3.1 启动基础依赖 (PostgreSQL & Redis)
如果您已安装 Docker，可使用 Docker Compose 启动数据库服务：
```bash
docker compose up -d pg redis
```

### 3.2 启动后端服务
```bash
# 1. 同步 Python 依赖环境 (使用 uv)
uv sync

# 2. 执行数据库迁移 (初始化全部数据表与内置资源)
uv run alembic upgrade head

# 3. 启动 FastAPI 开发服务器
uv run uvicorn agentplatform.main:app --reload --port 8000
```

### 3.3 启动前端 WebUI
```bash
cd web
npm install
npm run dev
```
访问 `http://localhost:3000` 即可进入对话工作台。

---

## 4. 容器化一键部署 (Docker Compose)

在生产或测试服务器中，可直接通过 `docker-compose.yml` 启动全套服务：

```bash
docker compose up -d --build
```

服务状态检查：
```bash
docker compose ps
docker compose logs -f api
```

---

## 5. 生产环境最佳实践

1. **数据库迁移**：
   在发布新版本时，在启动后端容器前运行迁移任务：
   ```bash
   uv run alembic upgrade head
   ```
2. **Nginx 反向代理配置**：
   对于 SSE 流式接口 `/api/chat/sessions/*/messages`，请确保 Nginx 关闭缓存并启用分块传输：
   ```nginx
   location /api/ {
       proxy_pass http://localhost:8000;
       proxy_http_version 1.1;
       proxy_set_header Connection '';
       proxy_buffering off;
       proxy_cache off;
       chunked_transfer_encoding on;
   }
   ```
3. **Secret Key 安全**：
   平台使用 `SECRET_KEY` 派生 Fernet 密钥加密存储大模型 API Key，生产环境务必确保密钥唯一且妥善保管。
