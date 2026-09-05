---
name: agentplatform-plugin-dev
description: Comprehensive development guide, shared skill/tool catalog, and 22 UI ContentBlocks specification for AgentPlatform plugins.
---

# AgentPlatform 智能体插件开发专属指南

## 🌟 平台核心优势与三大特色
1. **细粒度能力复用 (Skill & Tool Registry)**：
   - 平台维护公共注册表，内置通用技能与工具（`tool:pdf_parse@^1.0`、`skill:summarize@^1.0`、`skill:structured_output@^1.0`）。
   - 插件通过 `depends_on` 声明复合 SemVer 版本约束（`^`、`~`、`>=`），实现跨插件高效复用与组合。
2. **AI-Native 插件 SDK 与 CLI 工具链**：
   - 提供简洁优雅的 Python SDK（`@skill`、`@tool` 装饰器）。
   - CLI 提供 `init` / `registry` / `widgets` / `validate` / `dev` / `test` / `deploy` / `chat` / `update` 全套闭环。
3. **消息信封与 22 种富交互组件 (ContentBlocks)**：
   - 全面采用 `Message = {role, blocks[]}` 消息信封。
   - 智能体可通过 `output_block` 工具调用 22 种内置组件（展示类 8 种、交互输入类 11 种、反馈动作类 3 种）。

---

## ⚠️ 架构红线与开发边界约束 (CRITICAL BOUNDARIES)
1. **工作区边界严格隔离**：
   - 插件开发者的所有工作（代码编写、单测、调试、文件修改）必须且只能在**当前插件工程目录**内进行。
   - **严禁**搜索、读取、修改或打补丁到外部平台源码目录，也**严禁**对外部平台源码执行 `git pull` 或 git 操作。
   - 平台与插件是完全解耦的 Client-Server 架构：平台作为远端 HTTP 服务提供 API 与包下载。
2. **SDK 与 CLI 依赖管理**：
   - 插件环境所需轻量依赖为 `agentplatform`（含 SDK 与 CLI）+ `pyyaml` + `pytest`。
   - 严禁在插件环境安装平台服务端底层数据库/网关依赖（如 `sqlalchemy`, `asyncpg`, `alembic`, `fastapi`, `redis` 等）。
3. **闭环自愈原则**：
   - 若 `agentplatform validate` 或测试报错，请根据结构化 JSON 提示原地检查并修正插件内的 `plugin.yaml`、参数 `schema` 或实现代码，直至全部通过。

---

## 💾 插件持久化数据目录与环境变量约定
1. **专属稳定目录**：
   - 路径约定：`~/.agentplatform/plugins/<plugin_name>/data/`
   - 生命周期：与插件工程代码解耦，覆盖重新部署与版本升级时配置文件不丢失。
2. **环境变量与 SDK 访问**：
   - `AGENTPLATFORM_PLUGIN_DATA_DIR`：指向该持久化目录绝对路径。
   - `AGENTPLATFORM_BASE_URL`：指向平台服务根地址（默认 `http://localhost:8000`）。
   - Python 代码访问：
     ```python
     from agentplatform.sdk import get_plugin_data_dir, get_base_url
     data_dir = get_plugin_data_dir()
     base_url = get_base_url()
     ```

---

## 🌐 端侧真机工具契约规范 (tool:browser_wechat_draft)
1. **架构与零凭据设计**：
   - 属于端侧真机自动化工具，底层通过 WebSocket 隧道经本地 Chrome 扩展（BrowserAgent）直接复用用户在浏览器中当前已登录的公众平台 (`mp.weixin.qq.com`) 会话。
   - 插件侧与服务端**零凭据**，无需配置或持久化任何 AppID、AppSecret、Cookie、账号密码或隧道连接配置。
2. **调用参数契约**：
   - `title`: 图文标题 (必填)
   - `html_content`: 100% 全内联样式排版 HTML 正文 (必填)
   - `author`: 作者 (可选)
   - `digest`: 120 字摘要 (可选)
   - `theme`: 主题风格 (可选)

---

## 🏷️ 插件中文展示名称约定 (display_name)
- **清单声明**：在 `plugin.yaml` 中推荐声明 `display_name`（如 `display_name: 微信公众号写作助手`）。
- **用户呈现**：平台在助手广场、聊天页面顶部和会话抽屉列表中将优先展示友好的中文名称，同时在副标或角标呈现英文技术标识 `name`。
- **智能兼容**：若未显式指定，平台服务端将智能从 `description` 前缀推导或安全回退到英文 `name`。

---

## 🛠️ 常用开发命令
- **查阅公共技能与工具**：`agentplatform registry`
- **查阅 22 种富交互控件**：`agentplatform widgets`
- **新建插件脚手架**：`agentplatform init <plugin_name>`
- **静态代码与清单校验**：`agentplatform validate <path>`
- **本地终端交互调试**：`agentplatform dev <path>`
- **执行自动化用例**：`agentplatform test <path>`
- **一键部署到平台**：`agentplatform deploy <path> --target http://localhost:8000`
- **一键从远程平台同步升级**：`agentplatform update`

---

## 🔄 自然语言一键远程升级指令 (REMOTE AUTO-UPGRADE DIRECTIVE)
- 当开发者说「远程更新平台 CLI」、「更新 CLI」、「升级平台」、「同步规范」或「更新一下」时：
  1. **严禁** 去外部平台源码目录执行 git pull 或查看 git 状态；
  2. **严禁** 弹出多选菜单打断用户；
  3. **立即在后台直接执行命令**：`agentplatform update`；
     （若提示找不到 agentplatform 命令，则执行：`pip install --upgrade http://localhost:8000/api/specs/package.tar.gz && agentplatform update`）
  4. 该命令会自动通过 HTTP 从远程平台服务器拉取最新 SDK 代码包与规范；
  5. 执行完毕后向开发者回复简短确认。
