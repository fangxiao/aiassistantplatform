# agentplatform 项目

> 通用工作方式(减少确认打扰)与文档驱动开发流程见全局 `~/.claude/CLAUDE.md`,本文件仅记录项目特定信息。

## 项目状态

- AI 助手开发与分发平台,第一特色为「可复用 skill/tool + 显式调用」;定位与差异化见 [docs/vision.md](docs/vision.md)。
- git 已初始化(`main` 分支),远程仓库 [fangxiao/aiassistantplatform](https://github.com/fangxiao/aiassistantplatform)。
- 阶段 0-3 完成:愿景、需求(v1.2.1)、设计(001-006,002 已定稿)、ADR 0001/0002、任务拆解;已进入实现阶段(阶段 4)。
- M0 脚手架已完成(2026-08-13):uv 单项目(包名 `agentplatform`,规避 stdlib `platform` 模块冲突)+ Next.js 14 手工脚手架 + docker-compose 四服务 + SQLAlchemy Base/Alembic。
- 技术栈:Python(FastAPI)+ React(Next.js)+ PostgreSQL + Redis,docker-compose 单机部署;选型见 [docs/requirements/001-product-requirements.md](docs/requirements/001-product-requirements.md) §6。

## 项目结构(M0 已建立)

- `agentplatform/` 后端(FastAPI,含插件 SDK `agentplatform.sdk`)
- `web/` 前端(Next.js)
- `migrations/` Alembic 迁移(连接配置见 `alembic.ini`)
- `docker-compose.yml` 单机部署(pg/redis/api/web)
- `docs/` 产品 / 设计 / 任务 / ADR 文档

> 目录按 [docs/tasks/001-task-breakdown.md](docs/tasks/001-task-breakdown.md) M0 脚手架任务建立。

## 项目特定约定

- 文档驱动:每阶段产出文档经确认后才进入下一阶段;文档与代码不一致时先更新文档。
- 命令白名单见 `.claude/settings.json`(实现阶段按需补充)。
- 引用代码用 `file_path:line_number` 格式。

## ECC 项目级安装

- `.claude/` 下除 `settings.json` 外均为 ECC 托管文件(agents/commands/skills/rules/hooks/ecc/scripts/mcp-configs 等),已加入 `.gitignore`,不入库。
- 复现安装(先在 Claude Code 中添加 ECC 插件市场并安装插件,再执行项目级安装):

  ```bash
  # 前置:/plugin marketplace add affaan-m/ECC  然后 /plugin install ecc@ecc
  bash ~/.claude/plugins/marketplaces/ecc/install.sh --target claude-project python typescript
  ```

- 详见 [ECC 仓库](https://github.com/affaan-m/ECC);安装状态见 `.claude/ecc/install-state.json`(本地,不入库)。
