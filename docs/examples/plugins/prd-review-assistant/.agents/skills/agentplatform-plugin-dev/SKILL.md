---
name: agentplatform-plugin-dev
description: AgentPlatform 插件开发与共享能力指南
---

# 🤖 AgentPlatform 智能体插件开发指南 (针对 AI Assistant / Claude Code / Antigravity / Cursor)

你当前位于一个 **AgentPlatform 智能体插件工程** 中。你的任务是协助开发者设计、实现、测试与部署这个专属领域智能体助手。

---

## ⚠️ 架构红线与开发边界约束 (CRITICAL BOUNDARIES)
1. **工作区边界严格隔离**：
    - 你的所有工作（代码编写、单测、调试、文件修改）必须且只能在**当前插件工程目录**内进行。
    - **严禁**搜索、读取、修改或打补丁到外部平台源码目录（如平台后端或 SDK 源码），也**严禁**对外部平台源码执行 `git pull` 或 git 操作。
    - 平台与插件是完全解耦的 Client-Server 架构：平台作为远端 HTTP 服务提供 API 与包下载。
 2. **SDK 与 CLI 依赖管理**：
    - 插件环境所需轻量依赖为 `agentplatform`（含 SDK 与 CLI）+ `pyyaml` + `pytest`。
    - 严禁在插件环境安装平台服务端底层数据库/网关依赖（如 `sqlalchemy`, `asyncpg`, `alembic`, `fastapi`, `redis` 等）。
 3. **闭环自愈原则**：
    - 若 `agentplatform validate` 或测试报错，请根据结构化 JSON 提示原地检查并修正插件内的 `plugin.yaml`、参数 `schema` 或实现代码，直至全部通过。

---

## 1. 平台公共内置能力 (可在 plugin.yaml 的 depends_on 中直接复用)
无需自行重复编写底层解析与算法，平台已内置高稳定性的基础工具与技能：
- `tool:pdf_parse@^1.0` : 确定性 PDF 文件文本与结构解析提取 (输入: `file_path`)
- `skill:summarize@^1.0` : 针对长文本/文档的多维度核心摘要提取 (参数: `text`, `style`, `max_words`)
- `skill:structured_output@^1.0` : 结构化 JSON 数据抽取与字段规范化 (参数: `text`, `schema_desc`)

**依赖声明语法示例 (`plugin.yaml`)**：
```yaml
depends_on:
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0
  - skill:structured_output@^1.0
```

---

## 2. 插件工程架构规范
- `plugin.yaml` : 核心清单，声明插件名称、模型、版本、公共依赖 (`depends_on`)、自有 skills 与 tools。
- `pyproject.toml` : 插件工程轻量依赖配置 (`agentplatform`, `pyyaml`, `pytest`)。
- `skills/` : 编写 Prompt 模板与思考能力的技能。使用 `@skill(id="skill:...", version="...")` 装饰。
- `tools/` : 编写纯确定性 Python 计算/数据处理逻辑。使用 `@tool(id="tool:...", version="...")` 装饰。
- `test/` : 存放单元测试 (`test_*.py` 供 pytest) 与自动化用例 (`test_cases.yaml` 供 `agentplatform test`)。

---

## 3. 22 种富交互组件 (ContentBlocks) 输出
如果希望智能体在前端 Web 界面呈现富交互效果，可让模型调用特殊工具 `output_block({type, data, meta})`：
- **展示类 (8)**:
  - `markdown` (富文本), `code` (代码高亮带复制), `table` (多列排序表格), `card` (卡片容器), `collapsible` (折叠面板), `image` (安全图片预览), `file` (文件下载条目), `mermaid` (图表流程图).
- **交互输入类 (11)**:
  - `input.text` (单行输入), `input.textarea` (多行文本), `input.number` (数字输入), `input.select` (下拉选择), `input.radio` (单选组), `input.checkbox` (多选组), `input.toggle` (开关), `input.date` (日期), `input.file` (文件上传), `input.confirm` (确认操作框), `input.form` (复合表单).
- **反馈动作类 (3)**:
  - `action.copy` (一键复制文本), `action.thumbs` (点赞点踩打标), `action.regenerate` (重新生成动作).

**示例：输出交互式确认与表单控件**
```json
{
  "type": "input.confirm",
  "data": {
    "text": "是否确认将该 PRD 评审报告导出为 PDF 格式？",
    "action": "export_pdf_confirm",
    "confirm_text": "确认导出",
    "cancel_text": "稍后再说"
  }
}
```

---

## 4. 你的标准自愈开发流水线
每当你生成或修改代码后，请按序执行以下命令验证：
1. **单元测试**: `pytest` (测试 tools/skills 内部 Python 逻辑)
2. **静态校验**: `agentplatform validate .`
   - 若返回 `errors`，根据报错 JSON 原地修正代码，直至 `ok: true`。
3. **用例测试**: `agentplatform test .`
4. **查阅共享资源**: `agentplatform registry`
5. **查阅可用控件**: `agentplatform widgets`
6. **本地对话冒烟**: `agentplatform dev .`
7. **一键部署发布**: `agentplatform deploy .`

---

## 5. 本地人肉测试与双模式工作流规范 (LOCAL HUMAN TESTING PROTOCOL)
1. **用户模拟测试模式 (User Roleplay / 人肉测试)**：
   - 触发暗号：当开发者说「我来测」、「开始测试」、「人肉测试」或直接发送普通业务指令时。
   - 核心行为：
     1. 立即进入本插件专属的智能体角色（Persona）；
     2. 在后台静默调用 `agentplatform chat "<用户输入>"` 或静默调用本地 tools/skills，**严禁输出任何 bash 命令、Python 代码片段或调试日志**；
     3. 自动维持多轮会话记忆（继承前序参数与上下文）；
     4. 完全以面向终端用户的自然口吻输出最终助手的 Markdown 回答与图表；
     5. 严禁向用户暴露底层插件配置、示例断言或代码实现。
2. **开发者模式 (Developer Mode)**：
   - 触发暗号：当开发者说「切回开发」、「改代码」、「修 bug」或提出代码修改需求时。
   - 行为要求：恢复为资深研发伙伴，协助开发者分析代码、编写单测、修复 Bug 并执行 validate。

---

## 6. 自然语言一键远程升级指令 (REMOTE AUTO-UPGRADE DIRECTIVE)
- 当开发者说「远程更新平台 CLI」、「更新 CLI」、「升级平台」、「同步规范」或「更新一下」时：
  1. **严禁** 去外部平台源码目录执行 git pull 或查看平台 git 状态！
  2. **严禁** 弹出多选菜单或询问打断用户！
  3. **立即在后台直接执行命令**：`agentplatform update`；
     （若提示找不到 agentplatform 命令，则执行：`pip install --upgrade http://localhost:8000/api/specs/package.tar.gz && agentplatform update`）
  4. 该命令会自动通过 HTTP 从远程平台服务器拉取最新 SDK 代码包与规范；
  5. 执行完毕后向开发者回复简短确认。
