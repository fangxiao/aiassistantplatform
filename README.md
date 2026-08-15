# AgentPlatform (AI Assistant Platform)

> 现代化、高可复用、全链路闭环的大模型智能体平台 (FastAPI + Next.js 14 + PostgreSQL + Redis)。
> 支持 **Skill/Tool 细粒度注册复用**、**AI-Native 插件 SDK & CLI 工具链**、**22 种富交互组件 (ContentBlocks) 调度** 与 **端到端助手市场**。

---

## 🌟 核心特色

1. **第一特色 · 细粒度能力复用 (Skill & Tool Registry)**：
   - 平台维护公共注册表，内置通用技能与工具（如 `pdf_parse`、`summarize`、`structured_output`）。
   - 插件通过 `depends_on` 声明复合 SemVer 版本约束（`^`、`~`、`>=`），实现跨插件高效复用与组合。
2. **第二特色 · AI-Native 插件 SDK 与 CLI 工具链**：
   - 提供简洁优雅的 Python SDK（`@skill`、`@tool` 装饰器）。
   - CLI 支持 `init` / `validate` / `dev` / `test` / `deploy` / `logs` 全套开发调试与一键部署。
3. **第三特色 · 消息信封与 22 种富交互组件 (M7)**：
   - 全面采用 `Message = {role, blocks[]}` 消息信封，替代传统简单纯文本。
   - 内置 22 种 Renderer（Markdown、代码高亮带复制、可排序列结构表格、Card 容器、折叠面板、图片放大、附件、Mermaid 图表，以及 Form、Confirm、Select 等输入控件与回传链路）。
   - 自动支持嵌套深度限制（$\le 3$）与优雅降级。
4. **全套工作台与管理中心 (M8)**：
   - **对话工作台 (`/`)**：集成折叠式历史会话抽屉、SSE 实时打字机流式输出、工具调用轨迹追踪。
   - **助手广场 (`/assistants`)**：插件助手市场，支持实时检索、查看版本/模型/依赖标签，一键发起对话。
   - **开发者管理中心 (`/developer`)**：插件清单查看、状态启停、安全卸载与 OpenAI 兼容大模型端点管理。

---

## 🏗️ 架构概览

```
[Web 前端 (Next.js 14)]
  ├─ 对话工作台 (/) ── SessionDrawer + BlockRenderer (22 种内置组件 + 降级兜底)
  ├─ 助手广场 (/assistants) ── 浏览/搜索插件助手 -> 一键创建专属会话
  ├─ 开发者中心 (/developer) ── 插件清单管理 + LLM 网关端点配置
  └─ 交互回传 ── POST /api/chat/sessions/{sid}/blocks/{bid}/interact
                    ↓
[后端核心 (FastAPI + SQLAlchemy)]
  ├─ LLM 网关 & 路由 ── OpenAI 兼容流式转发 + Key 加密存储 (Fernet)
  ├─ 注册表服务 ── 平台内置/私有 Skill & Tool 复合版本约束解析
  ├─ Agent 调度循环 ── 显式 Function Calling 编排 + 多轮自纠 + output_block
  ├─ 交互与审计服务 ── 记录 interact_events 审计表并分发 Action
  └─ 认证与安全 ── Bcrypt 密码哈希 + PyJWT Bearer 拦截
                    ↓
[存储层 (PostgreSQL 16 & Redis 7)]
```

---

## 🚀 快速开始

### 1. 启动基础设施 (PostgreSQL + Redis)
```bash
docker compose up -d pg redis
```

### 2. 启动后端 API
```bash
# 同步环境并执行数据库迁移
uv sync
uv run alembic upgrade head

# 启动 FastAPI 服务
uv run uvicorn agentplatform.main:app --reload --port 8000
```

### 3. 启动前端 WebUI
```bash
cd web
npm install
npm run dev
```
打开浏览器访问 [http://localhost:3000](http://localhost:3000) 即可开始使用。

---

## 🛠️ CLI 插件开发与部署

```bash
# 快速初始化一个助手插件
uv run python -m agentplatform.cli.main init my-assistant

# 校验清单规范与代码合法性
uv run python -m agentplatform.cli.main validate ./my-assistant

# 本地交互式调试 (不依赖远程服务器)
uv run python -m agentplatform.cli.main dev ./my-assistant

# 执行自动化测试用例
uv run python -m agentplatform.cli.main test ./my-assistant

# 部署到平台
uv run python -m agentplatform.cli.main deploy ./my-assistant --target http://localhost:8000
```

---

## 📚 详细文档

- [部署与运维指南](docs/deployment.md)
- [插件开发者开发指南](docs/plugin_development_guide.md)
- [系统设计文档](docs/design/)
- [示例插件：PRD 评审助手](docs/examples/plugins/prd-review-assistant/)

---

## 📋 里程碑达成矩阵 (M0 ~ M10)

| 里程碑 | 状态 | 交付内容 |
| :--- | :---: | :--- |
| **M0 · 项目脚手架与基础** | ✅ 已完成 | FastAPI + uv + SQLAlchemy + Next.js 14 + Docker Compose |
| **M1 · 认证与用户体系** | ✅ 已完成 | Users 表迁移、Bcrypt、PyJWT (HS256)、Auth API 与前端登录注册 |
| **M2 · Skill/Tool 注册表** | ✅ 已完成 | 复合版本约束解析、内置 PDF 解析/摘要/结构化输出能力 |
| **M3 · LLM 网关与模型路由** | ✅ 已完成 | OpenAI 兼容 SSE 客户端、Fernet 加密、模型精准匹配与默认路由 |
| **M4 · 插件动态加载与管理** | ✅ 已完成 | 插件动态加载器、依赖校验、启停/卸载/部署 API |
| **M5 · Agent 运行时调度循环**| ✅ 已完成 | Tool/Skill 显式调用编排、嵌套 LLM 调用与多轮自纠调度循环 |
| **M6 · 对话 API 与 SSE 流式**| ✅ 已完成 | 会话与消息信封管理、`delta`/`tool_call`/`done`/`error` 流式事件 |
| **M7 · 富交互组件体系** | ✅ 已完成 | `interact_events` 迁移、22 种 Renderer、深度防爆与交互回传 |
| **M8 · 前端 WebUI 平台** | ✅ 已完成 | 对话工作台、会话管理抽屉、助手广场、开发者控制台 |
| **M9 · 插件 SDK 与 CLI** | ✅ 已完成 | Python SDK 装饰器、CLI（init/validate/dev/test/deploy/logs） |
| **M10 · 集成与示例** | ✅ 已完成 | PRD 评审示例插件闭环、E2E 集成测试、全套部署与开发者指南 |
