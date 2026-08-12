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

## 6. CLI 命令(AI-native 开发闭环)

**定位**:CLI 是插件开发者在本地的开发-测试-部署工具,分两层:

| 层 | 命令 | 说明 |
|----|------|------|
| **本地开发层**(不依赖远程平台) | `init` / `validate` / `dev` / `test` | 脚手架、校验、本地对话、测试用例 |
| **远程部署层**(与平台交互) | `deploy` / `logs` | 打包部署、查日志 |

| 命令 | 作用 | 输出 |
|------|------|------|
| `agentplatform init [name]` | 生成脚手架 | 创建目录与模板 |
| `agentplatform validate` | 校验清单/依赖/命名空间/规范 | **结构化 JSON**(AI 易解析) |
| `agentplatform dev` | 本地对话调试(本地 LLM 配置见下) | 交互式对话 + 事件流 |
| `agentplatform test` | 跑测试用例(`test/*.yaml`) | 用例结果(结构化,每例 pass/fail + 断言差异) |
| `agentplatform deploy ./path --target <url>` | 部署到平台(**内置准入**,见下) | plugin_id + 状态 |
| `agentplatform logs --target <url>` | 查日志 | 结构化日志 |

### 6.1 `dev` 本地运行
- 本地 `.env` 配置 OpenAI 兼容端点,与平台**同一协议**(`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL`)
- 不依赖远程平台即可启动对话,含 skill/tool 调用与 renderer 渲染(本地预览)
- 复用 001 §F6 的 OpenAI 兼容协议,保证"本地跑的 = 平台上跑的"

### 6.2 `test` 测试用例
```
test/
├── basic.yaml       # 对话用例
└── ...
```
```yaml
# test/basic.yaml
- name: 解析 PDF 并总结
  input: "帮我解析这份 PDF 并总结要点"
  expect:
    tool_calls: [tool:pdf_parse]        # 期望发起的调用
    output_contains: ["总结"]            # 期望输出包含
  # 可选: files: [./fixtures/sample.pdf]  # 附带文件
```
- `test` 跑完输出结构化结果(每例 pass/fail + 断言差异),AI 可据此修复

### 6.3 部署准入(方案 A)
- `deploy` **内置强制 `validate`**:清单 / 依赖 / 命名空间任一不过 → 拒绝部署,返回结构化错误
- `test` **可选但有则必过**:若 `test/` 目录存在,`deploy` 前自动跑;失败 → 阻止部署
- 保证"没校验 / 没测(有测试时)就不上线"

## 7. 部署协议
`agentplatform deploy` 流程:
1. **准入检查**(§6.3):CLI 本地跑 `validate`(强制)+ `test`(若存在 `test/`,有则必过)
2. 打包插件目录(tar)
3. `POST /api/plugins/deploy`(带开发者 token + 包)
4. 平台:再次校验清单 -> 解析 `depends_on`(注册表校验版本)-> 校验命名空间/不覆盖内置 -> 登记自有 skill/tool -> 进程内加载
5. 返回 `{plugin_id, status}`

> 平台侧校验独立于 CLI 本地准入——**以平台侧为准**,CLI 准入是"提前发现问题"的加速器。

## 8. AI-native 开发支持(vision 特色二)
- CLI 输出**结构化 JSON**,便于 Claude Code 解析与驱动
- `validate` 错误信息**可操作**(指明位置与修复建议,AI 可据此修复)
- 平台提供**插件开发规范文档**,可作为 Claude Code 的 skill/context 加载,让 AI 按规范自主开发
- 完整闭环:`init` -> 编写 -> `validate` -> `dev` / `test`(本地验证)-> `deploy` -> `logs`,全程可被 AI 驱动
- **部署准入**(§6.3):`deploy` 内置强制 `validate` + 有 `test/` 则必过——"本地验证通过后才允许部署"

---

## 9. 平台对插件开发者的约束

> 约束按强制力分层,对齐 001 §5"可信开发者/内部部署"假设(尽力而为,不做对抗性隔离)。

### 9.1 部署期强制(硬门槛,拦在 deploy 前)

| 约束 | 说明 |
|------|------|
| 清单 schema 合法 | `validate` 强制 |
| 依赖存在 + 版本兼容 | 002 §F-ST-5,失败拒绝部署 |
| 命名空间合法 | renderer 带 `<plugin_id>.`,skill/tool 全局唯一(ADR 0001) |
| 不覆盖内置资源 | 002 §F-ST-3.5.2,同 id 部署失败 |
| 不依赖插件 / 不包装共享资源 | 002 §F-ST-3.5.3 / F-ST-3.5.5 |
| 声明 model 或接受平台默认 | 001 §F6.3(不声明 → 平台默认端点 `is_default`) |
| deploy 内置 validate | 006 §6.3(方案 A) |

### 9.2 运行期尽力而为(软约束)

| 约束 | 说明 |
|------|------|
| tool 危险操作白名单 | 001 §F2.4,配置化允许清单 |
| 插件包大小上限 | MVP 暂定 < 10MB(可调) |
| 会话并发上限 | 每插件并发会话上限(如 20,MVP 可调) |
| 调用频率限制 | 防单插件拖垮平台(对 /interact 与 tool 调用限流) |
| 日志大小 / 速率 | 防日志刷爆磁盘 |

### 9.3 生态约束(秩序)

| 约束 | 说明 |
|------|------|
| 共享资源生命周期 | 弃用 / 删除 / 版本规则(002 §F-ST-7) |
| 插件生命周期 | 启停 / 卸载 / 版本(001 §F1.7) |
| 不可对抗平台 | 进程内加载假设下,平台不承诺隔离恶意插件(001 §5) |

### 9.4 可观测义务
- 插件须经 SDK logger 输出结构化日志;不能静默吞错(错误必须冒泡到结构化日志)
- 注册表变更 / 部署 / 启停记审计日志
- 指标:tool/skill 调用次数与耗时(001 §5 可观测)
