# AgentPlatform 插件开发者指南 (AI-Native Plugin Guide)

AgentPlatform 采用 **Plugin 即 Assistant** 的轻量设计理念。开发者只需编写一份清单与若干 Python 函数或技能类，即可快速构建并部署专属领域的 AI 智能体助手。

---

## 1. 插件工程标准目录结构

使用 CLI 创建或手工编写的插件仓库结构如下：

```
my-assistant/
├── plugin.yaml          # 核心清单 (元信息、模型、依赖与自有资源)
├── skills/              # 自有 Skill 实现 (Python)
│   └── custom_skill.py
├── tools/               # 自有 Tool 实现 (Python)
│   └── custom_tool.py
├── test/                # 自动化测试用例 (YAML)
│   └── test_cases.yaml
└── pyproject.toml       # 依赖声明 (agentplatform-sdk)
```

---

## 2. 编写 `plugin.yaml` 清单

```yaml
name: prd-review-assistant
version: 0.1.0
description: PRD 文档评审专家助手，支持文档解析、智能评审与多维度评分
author: DeveloperName
model: deepseek-v4-flash          # 指定运行模型 (如 deepseek-v4-flash 或 gpt-4o)
depends_on:                       # 复用平台公共资源 (支持 ^/~ semver 约束)
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0
  - skill:structured_output@^1.0
skills:                           # 声明自有 Skill
  - id: skill:prd_review
    file: ./skills/prd_review.py
tools:                            # 声明自有 Tool
  - id: tool:prd_score
    file: ./tools/prd_score.py
```

---

## 3. 使用 Python SDK 编写 Skill 与 Tool

### 3.1 编写 Skill (`@skill`)
Skill 是带领域 Prompt 模板与参数渲染的复合能力单元：

```python
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
    def execute(self, ctx: Context, args: dict) -> str:
        # 可在渲染前清洗或补齐参数
        if not args.get("dimensions"):
            args["dimensions"] = "需求完整性与技术可行性"
        return self.render(args)
```

### 3.2 编写 Tool (`@tool`)
Tool 是纯确定性的本地或远程调用接口：

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

## 4. 使用 AI-Native CLI 进行全流程开发

平台提供了完整的 CLI 开发工具链：

```bash
# 1. 快速初始化插件脚手架
uv run python -m agentplatform.cli.main init my-assistant

# 2. 静态校验清单、命名空间与 Python 代码语法
uv run python -m agentplatform.cli.main validate ./my-assistant

# 3. 本地交互式调试对话 (直接在终端运行，无需依赖平台服务器)
uv run python -m agentplatform.cli.main dev ./my-assistant

# 4. 执行自动化测试用例
uv run python -m agentplatform.cli.main test ./my-assistant

# 5. 部署到平台 (自动准入校验、依赖解析并入库助手市场)
uv run python -m agentplatform.cli.main deploy ./my-assistant --target http://localhost:8000
```

---

## 5. 22 种富交互组件 (ContentBlocks) 输出

智能体可在对话中调用 `output_block` 工具输出丰富的富交互 UI 组件：

| 分类 | 支持组件类型 |
| :--- | :--- |
| **展示类 (8)** | `markdown`、`code`、`table`、`card`、`collapsible`、`image`、`file`、`mermaid` |
| **交互输入类 (11)** | `input.text`、`input.textarea`、`input.number`、`input.select`、`input.radio`、`input.checkbox`、`input.toggle`、`input.date`、`input.file`、`input.confirm`、`input.form` |
| **反馈动作类 (3)** | `action.copy`、`action.thumbs`、`action.regenerate` |

**示例：输出交互式确认框**
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
用户点击确认后，WebUI 将自动向 `/api/chat/sessions/{sid}/blocks/{bid}/interact` 提交回传，并在界面中追加执行结果。
