---
name: agentplatform-deploy-company
description: 给新公司开台——部署 AgentPlatform 独立实例并配置该公司专属大模型。当用户说"给新公司开台/部署平台/新客户部署"时使用。
---

# 给新公司开台(AI 执行手册)

你正在目标服务器上为一家新公司部署 AgentPlatform 独立实例。目标:30 分钟内
四容器跑起、该公司模型配置生效、管理员就绪、诊断全绿。**按序执行,每步验证后再进下一步。**

## 前置检查(先做,缺项直接向用户要,不要猜)

依次确认,缺什么就明确问用户要什么,拿到后再继续:

1. `docker --version` 与 `docker compose version` 可用;不可用则指导安装(Docker Desktop / `curl -fsSL https://get.docker.com | sh`)
2. **本向导依赖**(CLI 无需预装——clone 平台仓库后用 `uv run` 直接跑):
   - `git --version` 可用;不可用则装 git
   - `uv --version` 可用;不可用则 `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - **纯内网服务器**(不能出公网):确认公司有 pip 镜像(如 devpi/nexus)与 git 镜像,
     `UV_INDEX=<内网PyPI镜像>` 后再 `uv sync`;或直接从内网拷贝平台仓库压缩包解压使用
3. 向用户收集(**必须问,不可编造**):
   - 模型 Base URL(OpenAI 兼容,如 `https://api.xxx.com/v1`)
   - API Key
   - 默认模型名(如 `glm-5.3-flash`);可选:多模态模型名
4. 可选(问了用户,没有就跳过并在最终报告注明"未配置"):
   - 内网 GitLab 地址 + read_api PAT → 离职知识归档可用
   - 飞书自建应用 app_id/secret → 文档同步可用
   - 该服务器能否出公网 → 决定 `--with-search`

## 部署

```bash
git clone <平台仓库地址> agentplatform && cd agentplatform   # 仓库地址问用户
./deploy/deploy.sh [--with-search]    # 出公网才加 --with-search
```

观察输出;若构建失败按错误信息修复(常见:PyPI 超时 → 重跑;Dockerfile 已有
UV_HTTP_TIMEOUT=300 与可选 UV_INDEX 清华源)。

## 配置模型

```bash
cat >> .deploy.env << 'EOF'
OPENAI_BASE_URL=<用户提供的>
OPENAI_API_KEY=<用户提供的>
DEFAULT_MODEL=<用户提供的>
MULTIMODAL_MODEL=<可选>
EOF
docker compose up -d api
```

## 管理员初始化

1. 提示用户在 `http://<服务器IP>:3000/auth` 注册管理员账号,拿到邮箱后执行:

```bash
docker compose exec -T pg psql -U agentplatform -d agentplatform -c \
  "UPDATE users SET role='developer' WHERE email='<管理员邮箱>';"
```

## 验收(全绿才算完成)

```bash
curl -s http://localhost:8000/api/diagnostics | python3 -m json.tool
```

- LLm/Embedding 必须 `ok: true`;失败按下表处置后重测:
  - llm ❌ → 检查 `.deploy.env` 是否被容器加载(`docker compose exec api env | grep OPENAI`);key 是否有效
  - embedding ❌ → 让管理员在开发者中心加 `endpoint_type=embedding` 端点(如 Ollama bge-m3),或 .env 加 `KB_EMBEDDING_MODEL` 走主网关
- 确认 `curl http://localhost:3000` 与 `/status` 页面 200。

## 最终报告(必须输出)

- 部署地址(Web/API)、管理员邮箱
- 诊断六项结果(逐项 ✅/❌)
- 已配置:模型(base_url + 默认模型)、数据源能力(GitLab/飞书/搜索 各自"已配/未配")
- 建议:`./deploy/backup.sh` 加入 crontab;提醒 7 天后回来确认定时任务(晨报)是否按时执行

## 红线

- API Key 等凭据只写入 `.deploy.env`(已 gitignore),不要出现在报告或日志里
- 不修改平台源码来完成部署;遇到平台 bug 报告用户,不在现场改
