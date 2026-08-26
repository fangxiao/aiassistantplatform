# RFC 登记表 · 端云协同 Browser Agent 能力 (RFC-2026-001)

- 状态:**Proposed**
- 日期:2026-08-25
- 提出方:插件侧 (access-browser-assistant 开发者) → 平台侧接收
- 关联:[002-skill-tool-model](../design/002-skill-tool-model.md) · [003-ui-components](../design/003-ui-components.md) · [006-plugin-spec](../design/006-plugin-spec.md)

---

## 背景

端云协同 (Browser Agent + 通用 Agent) 体系下,插件 `access-browser-assistant` 提出 4 项平台级能力需求。核心边界原则:**基础设施平台做,领域逻辑插件做** —— 平台提供标准连接网关、端侧协议规范、通用 HTML/DOM 清洗提取与端侧动作指令组件;插件专注于多标签页交叉比对、竞品研报深度推理、SWOT 矩阵构建与业务洞察。

---

## 平台侧分诊结论

| # | RFC 项 | 平台侧结论 | 工作量 | 优先级 |
|---|--------|-----------|--------|--------|
| 0 | **交互回填续跑 agent**(端侧动作结果注入对话流继续推理) | 🔴 **端云协同地基,第一优先** | 中 | 🔴 P0 |
| 1 | `tool:html_cleaner` 网页正文/DOM 语义提取 | ✅ 采纳为内置工具 | 低 | 高 |
| 2 | Browser Extension 接入网关 + Session 握手 | ⚠️ 独立里程碑立项(降级为优化项,POC 后决策) | 高 | 中(延后) |
| 3 | `browser.*` 端侧执行类 ContentBlocks | ✅ 协议扩展(依赖 RFC-0) | 低-中 | 高 |
| 4 | `skill:cross_document_compare` 多文档横向比对 | ✅ 采纳为内置技能 | 低 | 高 |
| B | `depends_on` 可选依赖/回退语义 | ⚠️ 平台机制改进,独立登记 | 中 | 中 |

---

## RFC-0 · 交互回填续跑 agent(端云协同地基,🔴 P0)

### 问题:当前交互链路中断

端侧执行结果回传后,agent 无法继续推理。查 `interact/service.py` 确认:

- `POST /sessions/{sid}/blocks/{bid}/interact` 目前只做两件事:**记录审计 + 返回静态确认块**(`"已接收交互指令"`)
- 它**不会**把端侧执行结果回填给 agent loop,agent 不会收到这些数据去继续分析

这意味着即使 Chrome 插件通过 `interact` 回传了 `{rows: [...]}`,云端 Agent 也感知不到——链路在"回填"这一步断了。

### 根本原因

当前 agent loop(`loop.py`)是**同步阻塞**的:LLM 发起 tool_call → 执行 → 回填 → 再推理,一轮内完成。没有"等待外部异步结果"的暂停/恢复机制。

### 建议方案:4 层扩展

**1. 端侧工具登记与路由(🔴 新增,衔接环)**
browser.* 工具必须在平台**注册表登记 schema**(resource_id 如 `tool:browser.read_page`),这样 LLM 在 function calling 时才知道这些工具可选。agent loop 需要识别"端侧工具"类型——**不下发本地执行**,而是转由通道路由到端侧:

```python
# 当前: 所有工具都本地 execute (loop.py execute())
# 改造后:
async def execute(resource, arguments):
    if resource.impl_kind == "endpoint":  # 端侧工具
        return await route_to_endpoint(resource, arguments)  # 通过 tunnel/SSE 下发,等待回传
    return await execute_tool(resource, args)  # 本地工具不变
```

**2. 新增 `await_external` 输出块类型**
让 agent 在需要端侧执行时,产出 `output_block({type: "await_external", data: {action: "browser.action.extractData", ...}})`。
该块在 SSE 流中像普通 block 一样下发,但语义是"等待端侧结果回来才能继续"。

**3. 复用 `interact` 端点作为回传入口**
Chrome 插件执行完端侧动作后,调用现有 `POST /sessions/{sid}/blocks/{bid}/interact` 回传结果。
但 `interact` 的 handler 需要从"静态确认"升级为:

```python
# 当前: 只记录审计 + 返回静态确认
# 改造后:
async def handle_interaction(...):
    # 1. 记录审计(不变)
    # 2. 若 action 匹配等待中的 await_external 块:
    #    a. 将结果注入对话上下文(追加 system message 或 assistant message)
    #    b. 触发 agent loop 重新推理(续跑)
    #    c. 返回 SSE 流(不要静态确认)
```

**4. agent loop 支持"暂停/续跑"状态机**
在 `loop.py` 中引入一个"等待外部"状态:

```
LLM 推理 → 产出 await_external 块 → 暂停(等待 interact)
                                   ↓
                               interact 到达 → 注入结果 → 恢复推理 → 继续产出 SSE
```

### 为什么这是 P0(比 WebSocket 网关更优先)

| 要解决的问题 | 当前状态 | 依赖 |
|------------|---------|------|
| 端侧执行结果回填给 agent 继续推理 | ❌ 链路中断 | **必须修** |
| 下行下发动作指令 | ✅ 已有 SSE 可用 | 修复即可复用 |
| 上行回传结果 | ✅ 已有 interact 端点 | 修复即可复用 |
| 低延迟双向通信 | ❌ 无 WebSocket | 优化项,修完上述再立项 |

**结论**:WebSocket 只解决延迟问题,不解决能力问题。而 `interact` 回填续跑是**有无的问题**,直接决定端云协同能否跑通。

---

## RFC-1 · tool:html_cleaner(网页正文与 DOM 语义提取)

### 建议平台接口
```yaml
# 依赖声明: tool:html_cleaner@^1.0
inputs:
  html_content: string   # 原始 HTML 或 DOM 片段
  extract_tables: bool   # 是否专门结构化提取表格数据 (默认 true)
outputs:
  title: string
  cleaned_markdown: string
  tables_json: list
  metadata: dict
```

### 说明
- 与已有 `tool:pdf_parse` 对称的通用确定性工具;涉及网页/抓取/爬虫的插件都会复用。
- 建议基于 Readability / Trafilatura 类算法实现。

---

## RFC-2 · Browser Extension 接入网关(独立里程碑)

### 建议
- 平台提供统一扩展接入端点与双向通信网关(如 `/api/v1/browser/tunnel` 或 WebSocket 会话)。
- 职责:扩展身份认证 (Token/Pairing)、当前 Tab 活跃状态心跳、会话级上下文保持。
- 提供轻量官方 npm 包 `@agentplatform/extension-bridge`,插件 `import { AgentBridge } from '@agentplatform/extension-bridge'` 即可握手。
- **补充(插件侧深化)**:网关应直接对接**标准 AgentDriver 抽象**(如 `browseragent` 一类),而非各插件自造驱动。平台网关定位为"连接协议 + 能力适配层",上接云端智能体,下接任意实现 AgentDriver 接口的端侧引擎。

### 平台侧评估
- ⚠️ 这是**新的通信平面**(WebSocket 隧道 + 身份配对 + npm 包),非"加一个工具/技能"级别,独立立项。
- 现阶段插件可用现有 REST + SSE(平台已有 `/api/chat` SSE 流 + JWT 认证)先行,网关等平台下个里程碑。
- 建议引入标准 AgentDriver 抽象,保证未来多端(Chrome/Firefox/移动端/桌面)统一接入。

---

## RFC-3 · browser.* 端侧执行类 ContentBlocks(协议扩展)

### 建议新增端侧 Action 控件(两类:UI 指令 + 能力执行)

**A. UI 指令类(单向下发,无需返回)**:
| type | data | 用途 |
|------|------|------|
| `browser.highlight` | `{selector, color, tooltip}` | 高亮指定文本/CSS 选择器节点 |
| `browser.scroll_to` | `{selector, anchor}` | 平滑滚动到指定锚点 |
| `browser.open_tab` | `{url}` | 打开推荐关联标签页 |
| `browser.fill_form` | `{fields[]}` | 自动回填表单字段 |

**B. 能力执行类(双向:云端下发 → 端侧执行并返回结果)**:
| type | data | 用途 |
|------|------|------|
| `browser.action.readPage` | `{url?}` | 读取当前/指定页面 DOM 与正文 |
| `browser.action.extractData` | `{selector, extract[]}` | 按规则抽取结构化数据 |
| `browser.action.clickElement` | `{selector}` | 模拟点击指定元素 |

### 平台侧评估
- ContentBlock 信封的自然延伸(展示类 → 端侧动作类)。平台负责**定义块类型 + payload schema**,执行者是扩展本身。
- **语义注意**:能力执行类(B)不再是纯展示——云端下发后需**等待端侧返回结果并回填对话流**。这要求平台 ContentBlock 协议从单向 `output_block` 扩展出"动作下发 + 结果回传"的双向语义(可复用已有 `interact` 回传通道,见 [003-ui-components](../design/003-ui-components.md))。
- **🔴 依赖 RFC-0**:B 类控件的"结果回填续跑"能力由 RFC-0 提供。RFC-0 未实现前,B 类控件只能做"UI 指令"语义,无法完成端云协同闭环。建议先落 RFC-0,再落本项。
- 平台改动:能力目录 + 前端 renderer 注册 + 交互回传协议扩展,可作为快速迭代项。

---

## RFC-4 · skill:cross_document_compare(多文档/多实体横向比对)

### 建议平台接口
```yaml
# 依赖声明: skill:cross_document_compare@^1.0
inputs:
  entities: list[dict]      # [{name: "A", content: "..."}, {name: "B", content: "..."}]
  dimensions: list[string]  # ["功能覆盖", "价格模式", "优劣势"]
outputs:
  comparison_matrix: dict
  summary_markdown: string
```

### 平台侧评估
- 通用大模型能力(比对多份合同/研报/候选人/竞品),与 `summarize`、`structured_output` 同属平台第一特色范畴。
- **定位(插件侧深化)**:将多文档 / 多 Tab 的**横向矩阵抽取**沉淀为平台公共技能,供所有需要"多源数据重组对比"的插件复用(竞品研报、合同比对、多候选人评估等)。
- 本质是**组合技能**,可基于现有 skill 搭建,不需要新后端设施。

---

## 机制改进 B · depends_on 可选依赖/回退语义

### 问题
平台 `depends_on` 是**必选依赖**:部署时 `check_dependencies`(loader.py)发现缺失即失败。因此插件**无法** forward-declare 尚未上线的平台能力,也无法做到"平台有则用平台版、无则用插件本地同名实现"的零成本迁移。

### 建议
- 新增可选依赖语法(如 `depends_on: tool:html_cleaner@^1.0?` 或独立字段),平台解析时:有 → 用平台版;无 → 回退插件本地同名实现。
- 惠及所有插件,建议独立登记为平台机制改进。

---

## 插件侧实施策略(平滑演进,路径 A)

```
┌────────────────────────────────────────────────────────┐
│               access-browser-assistant                 │
├────────────────────────────────────────────────────────┤
│ 【自研/临时过渡层】 (独立命名空间 tool:access-browser_*)  │
│  • tools/html_distiller.py   本地高效纯 Python 提取降噪  │
│  • tools/matrix_generator.py 多维对比表格与图表生成器     │
│  • skills/tab_comparator.py  竞品研报多维交叉比对技能     │
│  • skills/sidepanel_insight.py 单Tab即时侧边栏洞察       │
├────────────────────────────────────────────────────────┤
│ 【平台标准交互层】                                       │
│  • 规范化 ContentBlocks (table, mermaid, card, confirm) │
│  • 预留 browser.* 动作 payload 协议规范                 │
└────────────────────────────────────────────────────────┘
```

### 命名空间约定(避免与平台未来 ID 冲突)
- 插件自研工具/技能使用 `tool:access-browser_*` / `skill:access-browser_*`,**不要**使用 `tool:html_cleaner` 这类与平台未来内置 ID 冲突的名字。
- 平台上线内置能力后,切换 `depends_on` + 接线(工具名),外层用户接口(ContentBlocks / 助手人设)保持不变。

---

## 端云标准通信协议规范 (Contract)

### 1. 多 Tab 数据打包上报格式 (Browser → AgentPlatform)

```json
{
  "plugin": "access-browser-assistant",
  "message": "请对以下竞品进行多维比对分析",
  "tabs": [
    {
      "tab_id": 101,
      "title": "Notion 定价与功能",
      "url": "https://www.notion.so/pricing",
      "summary": "root > header, main(table.pricing)",
      "extracted_data": {
        "hasHeader": true,
        "rows": [["Plus Plan", "$10/mo"], ["Business", "$15/mo"]]
      },
      "selected_text": "Plus Plan $10/mo"
    }
  ]
}
```

### 2. 智能体动作下发协议 (AgentPlatform → Browser)

```json
{
  "type": "TOOL_CALL",
  "callId": "call_9f8a12bc",
  "toolCall": {
    "name": "extractData",
    "args": { "selector": "table.pricing-matrix", "format": "json" }
  }
}
```

### 3. 端侧执行结果回传协议 (Browser → AgentPlatform)

```json
{
  "type": "TOOL_RESULT",
  "callId": "call_9f8a12bc",
  "result": { "ok": true, "data": { "hasHeader": true, "rows": [["基础版", "免费"], ["专业版", "99元/月"]] } }
}
```

---

## 实施推进路线图 (Roadmap)

| 阶段 | 目标 | 涉及工程与任务 | 预期效果 |
|------|------|----------------|----------|
| **第一阶段**(当前就绪) | 多 Tab 研报数据重组 | access-browser-assistant: tab_distiller / matrix_generator / tab_comparator;browseragent: 侧边栏加按钮发 HTTP 请求 | Chrome 侧边栏一键生成多竞品横向比对研报与 SWOT 矩阵 |
| **第二阶段** | 自然语言双向调度 | AgentPlatform: RFC-0(交互回填续跑) + 端侧工具登记路由;browseragent: background.ts 接通道监听 | 用户在通用 Agent 网页直接打字,自动远程操控 Chrome 执行提取与点击 |
| **第三阶段** | 平台公共能力沉淀 | AgentPlatform: 发布 `tool:html_cleaner`、`browser.*` 控件、`skill:cross_document_compare`;插件 plugin.yaml 直接 depends_on 复用 | 全平台其它 Agent 直接复用浏览器能力,架构进一步精简 |

> **平台侧对齐注记**:第二阶段依赖 RFC-0(交互回填续跑 agent)而非 WebSocket 网关先行——回填是"有无"问题,WebSocket 是延迟优化项(见 RFC-0 论证)。WebSocket 网关(P1)可在第二阶段内作为通道路由的承载实现,但不必前置。
