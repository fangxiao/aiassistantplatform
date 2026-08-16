# AgentPlatform 插件开发者指南 (AI-Native Plugin Developer Guide)

AgentPlatform 采用 **Plugin 即 Assistant** 的轻量设计理念。开发者只需编写一份 `plugin.yaml` 清单与若干 Python 函数或技能类，即可快速构建并部署专属领域的 AI 智能体助手。

---

## 🌟 1. 核心优势：平台共享能力注册表 (Skill & Tool Ecosystem)

平台将 **Skill** 与 **Tool** 提升为一等公民（First-class Citizens）。开发者在创建新插件时**严禁重复造轮子**，应优先复用平台公共注册表中已有的基础能力：

### 1.1 平台内置公共能力清单

| 资源 ID | 类型 | 说明 | 输入参数 / Schema 契约 | 依赖声明语法 |
| :--- | :---: | :--- | :--- | :--- |
| `tool:pdf_parse@^1.0` | **Tool (工具)** | 确定性 PDF 解析，提取文档纯文本 | `file_path`: string (PDF 文件路径) | `- tool:pdf_parse@^1.0` |
| `skill:summarize@^1.0` | **Skill (技能)** | 长文本智能多维度核心摘要提取 | `text`: string, `style`: "concise"\|"detailed", `max_words`: int | `- skill:summarize@^1.0` |
| `skill:structured_output@^1.0` | **Skill (技能)** | 从非结构化文本中精准提取目标 JSON 结构 | `instruction`: string, `json_schema`: object, `content`: string | `- skill:structured_output@^1.0` |

### 1.2 在 `plugin.yaml` 中声明共享依赖
插件只需在 `depends_on` 列表中声明语义化版本（SemVer，支持 `^`、`~`、`>=`）：

```yaml
name: contract-review-assistant
version: 0.1.0
description: 智能合同法务审查专家，复用平台 PDF 解析与结构化提取能力
model: deepseek-v4-flash
depends_on:
  - tool:pdf_parse@^1.0          # 复用平台共享工具：PDF 文本解析
  - skill:summarize@^1.0         # 复用平台共享技能：文本核心摘要
  - skill:structured_output@^1.0 # 复用平台共享技能：JSON 结构化提取
skills:
  - id: skill:contract_review
    file: ./skills/contract_review.py
tools:
  - id: tool:calc_penalty
    file: ./tools/calc_penalty.py
```

---

## 🎨 2. 核心优势：22 种富交互组件 (ContentBlocks) 调度

智能体可在对话中调用 `output_block` 工具输出丰富的富交互 UI 组件，超越传统纯文本对话：

| 分类 | 控件类型 (type) | 中文名称 | 核心应用场景与作用 |
| :--- | :--- | :--- | :--- |
| **展示类 (8)** | `markdown` | Markdown 文本 | 基础富文本排版、标题、加粗、列表 |
| | `code` | 代码高亮块 | 语法高亮代码展示，带一键复制功能 |
| | `table` | 结构化表格 | 多列结构化数据，前端支持动态列排序 |
| | `card` | 卡片容器 | 组合型卡片容器，支持嵌入子组件 |
| | `collapsible` | 折叠面板 | 收纳冗长日志、排查明细或技术细则 |
| | `image` | 安全图片预览 | 渲染图片并支持点击全屏放大 |
| | `file` | 文件下载附件 | 展示生成的文件名、体积与下载入口 |
| | `mermaid` | Mermaid 图表 | 渲染流程图、时序图、架构图与甘特图 |
| **交互输入类 (11)** | `input.text` | 单行输入框 | 采集单行文本（如关键字、标题、邮箱） |
| | `input.textarea` | 多行长文本框 | 采集大段需求描述、修改意见或长备注 |
| | `input.number` | 数字微调器 | 采集数值（如预算、天数、目标分值） |
| | `input.select` | 下拉选择框 | 多候选项时的空间收纳与单项选择 |
| | `input.radio` | 单选按钮组 | 2-4 个选项时的平铺直观单选 |
| | `input.checkbox` | 多选复选框 | 支持勾选多个属性、维度或标签 |
| | `input.toggle` | 状态开关 | 二元状态开关（开启/关闭、包含/排除） |
| | `input.date` | 日期选择器 | 选择交付日期、截止时间 |
| | `input.file` | 文件上传组件 | 引导用户在对话中上传补充文件 |
| | `input.confirm` | 确认操作框 | 包含确认与取消双动作的操作拦截框 |
| | `input.form` | 复合提交表单 | 多字段统一校验与一次性回传表单 |
| **反馈动作类 (3)** | `action.copy` | 一键复制按钮 | 快速将大段输出拷贝至用户系统剪贴板 |
| | `action.thumbs` | 点赞点踩打标 | 对助手特定回答进行质量反馈 |
| | `action.regenerate` | 重新生成按钮 | 引导用户换个视角或深度重新生成结果 |

### 2.1 智能体调用 `output_block` 输出示例

```json
{
  "type": "input.confirm",
  "data": {
    "text": "已发现该 PRD 存在 2 处未闭环的资金扣减异常分支，是否确认导出风险清单？",
    "action": "export_risk_list",
    "confirm_text": "🚀 立即导出",
    "cancel_text": "稍后再说"
  }
}
```

用户点击后，WebUI 自动将交互事件回传至平台后端，持久化至 `interact_events` 并驱动下一轮智能体决策。

---

## 🛠️ 3. 插件工程标准目录结构

使用 CLI 创建的插件工程结构如下：

```
my-assistant/
├── plugin.yaml          # 核心清单 (元信息、模型、depends_on 与自有资源)
├── skills/              # 自有 Skill 实现 (Python, Prompt + 参数处理)
│   └── custom_skill.py
├── tools/               # 自有 Tool 实现 (Python, 确定性计算与接口)
│   └── custom_tool.py
├── test/                # 自动化测试用例
│   └── test_cases.yaml
├── AGENTS.md / CLAUDE.md / .cursorrules # 全套 AI 编程助手协同规范
└── .agents/skills/      # Antigravity / Gemini 专属智能体技能包
```

---

## 💻 4. 使用 Python SDK 编写 Skill 与 Tool

### 4.1 编写 Skill (`@skill`)
```python
from typing import Any
from agentplatform.sdk import Context, Skill, skill

@skill(
    id="skill:prd_review",
    version="1.0.0",
    description="按完整性、可行性、风险等多维度深度评审 PRD 文档",
    schema={
        "type": "object",
        "properties": {
            "doc": {"type": "string", "description": "PRD 文档内容"},
            "dimensions": {"type": "string", "description": "评审维度"},
        },
        "required": ["doc"],
    },
    prompt="你是一个资深产品专家，请基于维度 {{dimensions}} 评审以下 PRD：\n{{doc}}",
)
class PRDReview(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        if not args.get("dimensions"):
            args["dimensions"] = "需求完整性与技术可行性"
        return self.render(args)
```

### 4.2 编写 Tool (`@tool`)
```python
import json
from agentplatform.sdk import tool

@tool(
    id="tool:prd_score",
    version="1.0.0",
    description="对 PRD 文本进行确定性质量与完整度综合打分 (0-100分)",
    schema={
        "type": "object",
        "properties": {
            "doc": {"type": "string", "description": "PRD 内容"},
        },
        "required": ["doc"],
    },
)
def prd_score(doc: str = "") -> str:
    score = 85
    return json.dumps({"score": score, "level": "A"}, ensure_ascii=False)
```

---

## 🚀 5. AI-Native CLI 全流程命令速查

```bash
# 1. 查阅平台公共内置/共享技能与工具注册表
uv run python -m agentplatform.cli.main registry

# 2. 查阅 22 种富交互 ContentBlock 控件清单与调用样例
uv run python -m agentplatform.cli.main widgets

# 3. 快速初始化插件脚手架 (自动注入 AI 规范与依赖模板)
uv run python -m agentplatform.cli.main init my-assistant

# 4. 静态校验清单、命名空间、依赖格式与 Python 语法
uv run python -m agentplatform.cli.main validate ./my-assistant

# 5. 本地交互式调试对话 (自动挂载 depends_on 共享能力，无需依赖平台服务器)
uv run python -m agentplatform.cli.main dev ./my-assistant

# 6. 执行自动化测试用例
uv run python -m agentplatform.cli.main test ./my-assistant

# 7. 一键部署到平台 (自动准入校验、依赖解析并入库助手市场)
uv run python -m agentplatform.cli.main deploy ./my-assistant --target http://localhost:8000
```

---

## 🤖 6. AI 结对编程与「人肉测试」双模式

当您使用 AI 编码助手（Antigravity、Claude Code、Cursor、Windsurf）打开插件工程时，AI 已默认获知全部平台规范：

1. **人肉测试模式**（暗号：「我来测」/「开始测试」/「进行冒烟」）：
   - AI 自动切换为该插件的角色（Persona），静默调用本地 tools 与 skills 模拟真实多轮对话；
   - 严禁向用户暴露 bash 指令或底层 Python 源码。
2. **开发者模式**（暗号：「切回开发」/「改代码」/「修 bug」）：
   - AI 恢复为资深架构师伙伴，协助编写单测、修复 Bug 并执行 `validate` 自愈闭环。
