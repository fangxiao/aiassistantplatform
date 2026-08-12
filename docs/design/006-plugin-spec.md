# 006 · 插件规范

- 文档版本:v0.1(草案)
- 日期:2026-08-11
- 流程阶段:阶段 2 · 设计
- 对应需求:F1、vision 特色二

---

## 1. 插件仓库结构(独立仓库)
```
my-assistant/
├── plugin.yaml          # 清单
├── skills/              # 自有 skill 定义(Python)
├── tools/               # 自有 tool 实现(Python)
├── renderers/           # (可选)自定义前端 renderer 包(构建产物)
│   └── dist/            #   构建后的 JS bundle,被 WebUI 动态 import
├── renderer-src/        # (可选)renderer 源码(React/TS),构建到 renderers/dist
└── pyproject.toml       # 依赖:platform.sdk
```

## 2. plugin.yaml 清单
```yaml
name: prd-review-assistant
version: 0.1.0
description: PRD 文档评审助手
author: <developer>
model: glm-5.2                      # 指定模型(vision: MVP 单一模型)
depends_on:                         # 引用公共 skill/tool(复用)
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0
  - skill:structured_output@^1.0
skills:                             # 自有 skill
  - id: skill:prd_review
    file: ./skills/prd_review.py
tools: []                           # 自有 tool
renderers:                          # 自定义前端 renderer(对齐 003 v2.0 §3.2 / ADR 0001)
  - name: my_plugin.review_card    # 必须带 <plugin_id>. 前缀
    package: "my-plugin-renderer@1.0.0"   # npm 包名 + 版本,WebUI 动态 import
    entry: "dist/index.js"         # 包入口
  - name: my_plugin.approval_button
    package: "my-plugin-renderer@1.0.0"
    entry: "dist/button.js"
```

## 3. skill 定义(Python + SDK)
```python
from platform.sdk import Skill, skill

@skill(id="skill:prd_review", version="1.0.0")
class PRDReview(Skill):
    description = "按维度评审 PRD"
    schema = { "type": "object", "properties": { "doc": {"type":"string"} } }
    prompt = "你是一个 PRD 评审专家...按以下维度评审:{{dimensions}}"

    def execute(self, ctx, args):
        # 简单 skill:返回 prompt 填充结果,由 agent 执行
        return self.render(args)
```

## 4. tool 定义
```python
from platform.sdk import tool

@tool(id="tool:pdf_parse", version="1.0.0")
def pdf_parse(file: str) -> str:
    """解析 PDF 为文本"""
    ...  # 实现
    return text
```

## 5. SDK(platform.sdk)
- 装饰器 `@skill` / `@tool` 注册元信息
- `Skill` / `Tool` 基类、`Context`、schema 工具
- 内置本地 dev 运行时(供 `agentplatform dev` 调用,不依赖远程平台)
- 独立发布为 Python 包

## 6. CLI 命令(AI-native)
| 命令 | 作用 | 输出 |
|------|------|------|
| `agentplatform init [name]` | 生成脚手架 | 创建目录与模板 |
| `agentplatform validate` | 校验清单/依赖/规范 | **结构化 JSON**(AI 易解析) |
| `agentplatform dev` | 本地运行调试 | 启动本地对话(含组件渲染) |
| `agentplatform deploy ./path --target <url>` | 部署到平台 | plugin_id + 状态 |
| `agentplatform logs --target <url>` | 查日志 | 结构化日志 |
| `agentplatform test` | 跑测试对话 | 用例结果 |

## 7. 部署协议
`agentplatform deploy` 流程:
1. `validate` 通过
2. 打包插件目录(tar)
3. `POST /api/plugins/deploy`(带开发者 token + 包)
4. 平台:校验清单 -> 解析 `depends_on`(注册表校验版本)-> 登记自有 skill/tool -> 进程内加载
5. 返回 `{plugin_id, status}`

## 8. AI-native 开发支持(vision 特色二)
- CLI 输出**结构化 JSON**,便于 Claude Code 解析与驱动
- `validate` 错误信息**可操作**(指明位置与修复建议,AI 可据此修复)
- 平台提供**插件开发规范文档**,可作为 Claude Code 的 skill/context 加载,让 AI 按规范自主开发
- 完整闭环:`init` -> 编写 -> `validate` -> `dev` 调试 -> `deploy` -> `logs`,全程可被 AI 驱动
