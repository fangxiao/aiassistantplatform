# 🤖 AgentPlatform 智能体平台与插件开发核心规范 (AGENTS.md)

本仓库是 **AgentPlatform (AI Assistant Platform)** 核心平台与插件开发生态根目录。

---

## 🌟 平台核心优势与三大特色

1. **第一特色 · 细粒度能力复用 (Skill & Tool Registry)**：
   - 平台维护公共注册表，内置通用技能与工具（`tool:pdf_parse@^1.0`、`skill:summarize@^1.0`、`skill:structured_output@^1.0`）。
   - 插件通过 `depends_on` 声明复合 SemVer 版本约束（`^`、`~`、`>=`），实现跨插件高效复用与组合。
2. **第二特色 · AI-Native 插件 SDK 与 CLI 工具链**：
   - 提供简洁优雅的 Python SDK（`@skill`、`@tool` 装饰器）。
   - CLI 提供 `init` / `registry` / `widgets` / `validate` / `dev` / `test` / `deploy` / `chat` / `update` 全套闭环。
3. **第三特色 · 消息信封与 22 种富交互组件 (ContentBlocks)**：
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

## 🛠️ 插件开发者核心指引

### 1. 插件工程标准目录结构
```
my-assistant/
├── plugin.yaml          # 清单文件 (声明元信息、模型、depends_on、skills 与 tools)
├── pyproject.toml       # 插件依赖声明 (agentplatform, pyyaml, pytest)
├── skills/              # 领域技能 (Prompt + 参数渲染，使用 @skill)
│   └── custom_skill.py
├── tools/               # 确定性工具 (Python 计算/接口，使用 @tool)
│   └── custom_tool.py
├── test/                # 自动化测试用例
│   └── test_cases.yaml
└── .agents/skills/      # AI 智能体开发技能规范
```

### 2. 常用开发命令
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
