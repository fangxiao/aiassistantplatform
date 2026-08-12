# agentplatform 消息展示扩展需求文档(PRD)

- 文档版本:v1.0
- 日期:2026-08-12
- 流程阶段:阶段 1 · 需求(增量)
- 对应主需求:[001-product-requirements.md](./001-product-requirements.md)
- 关系:**001 §F3 + §8.2 的细化扩展**;001 保持 v1.2 不动,本文档作为独立的 003 增量需求
- 相关需求:[002-skill-tool-sharing.md](./002-skill-tool-sharing.md)(skill/tool 共享机制)
- 对应设计:[../design/003-ui-components.md](../design/003-ui-components.md)

## 变更记录
- v1.0(2026-08-12):初稿。锁定 7 种展示类 renderer + 14 种交互控件最小集;明确消息信封协议与回传语义;定义容器型与嵌套规则;明确安全降级与 i18n 基线。
- v1.0(2026-08-12 同日补):新增 §F-MR-9 UI 扩展性边界(只支持 renderer 挂件);F-MR-8.5 引用 ADR 0001 命名空间规则。
- v1.0(2026-08-12 评审通过):定稿,无进一步修改。

---

## 1. 背景与目标

### 1.1 背景
001 §F3.2 承诺"插件可定义对话中的富交互组件(文本框、复选框、按钮)",但未定义协议细节。001 §8.2 明确把"组件 schema、渲染、回传"留待设计阶段。

本文档填补该缺口:把"消息该怎么渲染"从 WebUI 硬编码中解耦,改为**由插件通过 `platform.sdk` 声明 renderer**。同时把 v1.2 中仅"3 种基础类型"的范围扩展为**21 种 renderer 的明确清单**,并对每种给出数据 schema 与回传语义。

### 1.2 目标
- **解耦**:WebUI 端只维护 renderer registry 调度层,不实现具体渲染逻辑
- **可扩展**:新增一种展示形态 = 新增/更新一个插件,不需修改 WebUI 主仓库
- **可回传**:交互控件的用户操作必须能回到 agent loop,影响后续轮次(对齐 001 §F3.3)
- **可降级**:未知 renderer 类型不导致崩溃,有可观察的降级渲染与告警

### 1.3 非目标
- 不做富文本编辑器(用户在消息框内所见即所得编辑)
- 不做实时协同(多人同时编辑同一消息)
- 不做自定义 HTML / JS 注入(MVP 不开放任意代码执行)
- 不做服务端渲染(SSR)——renderer 仅在 WebUI 端执行

---

## 2. 用户角色

沿用 001 §2 三类角色,本文档涉及的角色焦点:

| 角色 | 与本文档相关的关切 |
|------|-------------------|
| 开发者(Developer) | 通过 `platform.sdk` 注册 renderer;提供数据 schema;实现交互回传 handler |
| 使用者(End User) | 在对话中看到/操作富组件;操作结果影响对话 |
| 平台开发者(WebUI 维护者) | 维护 registry 调度层、内置 renderer 实现、安全降级 |

---

## 3. 核心概念

| 概念 | 定义 |
|------|------|
| **Message Envelope** | 一条消息的统一结构:`{role, blocks: ContentBlock[]}`。一条消息可由多个 block 组成(例如"一段 markdown + 一张图片 + 一个按钮") |
| **ContentBlock** | 消息的最小渲染单元:`{type: <renderer_name>, data: <renderer_specific>, meta?: {id, group?} }` |
| **Renderer** | 消息块到 React 组件的映射,由插件或 WebUI 内置实现 |
| **Renderer Registry** | 全局注册表,key = renderer name,value = `{Component, schema, interactive: bool, accept_data?: bool}` |
| **交互回传(Callback)** | 用户对交互控件的操作通过 WebSocket/HTTP 回到后端,后端路由到对应插件的 handler,handler 返回新 block 列表,WebUI 续渲染 |
| **容器型 Renderer** | 能包含子 block 的 renderer(card / collapsible / form) |
| **降级渲染** | 未知或出错 renderer 的兜底显示:展示原始 data + 警告标识 |

### 3.1 消息信封示例
```json
{
  "role": "assistant",
  "blocks": [
    {"type": "markdown", "data": {"text": "下面是分析结果:"}},
    {"type": "table", "data": {"columns": ["指标", "值"], "rows": [["准确率", "0.92"]]}},
    {"type": "button", "data": {"label": "重新生成", "action": "regenerate", "args": {}}}
  ]
}
```

---

## 4. 功能需求

### F-MR-1 消息信封协议(平台统一)
- F-MR-1.1 平台定义统一消息结构 `Message = {role, blocks[]}`,替换现有"纯文本 content"字段
- F-MR-1.2 role 取值沿用 OpenAI 风格:`system` / `user` / `assistant` / `tool`
- F-MR-1.3 block 的 `type` 字段即为 renderer 名称,**全局唯一,反向 DNS 风格**(`markdown`、`pdf.card`、`weather.forecast` 等)
- F-MR-1.4 `data` 字段结构由该 renderer 的 schema 描述,平台不强校验(由 renderer 自身校验)
- F-MR-1.5 `meta.id` 用于交互回传时定位 block;`meta.group` 用于将多个 block 标记为同一逻辑单元
- F-MR-1.6 兼容模式:旧消息仅有 `content: string` 时,前端按 `{type: "markdown", data: {text: content}}` 渲染(向后兼容,不留历史分支)

### F-MR-2 展示类 Renderer(7 种,MVP 必交付)

| type | data schema | 关键交互 | 说明 |
|------|-------------|----------|------|
| `markdown` | `{text: string}` | 链接点击(可选) | 默认 renderer,支持 GFM;`text` 字段空时降级为空 |
| `code` | `{lang: string, source: string, filename?: string}` | 复制 | 语法高亮(基于 lang);filename 可选,显示在 header |
| `image` | `{url: string, alt?: string, width?: number, height?: number}` | 预览、下载 | url 必须 HTTPS;本地文件经 `/api/files/{id}` 代理 |
| `file` | `{name: string, url: string, mime: string, size: number}` | 下载 | 大文件显示大小;预览条件 = mime 在允许列表(图片/PDF/文本) |
| `card` | `{title?: string, body_blocks?: ContentBlock[], actions?: ContentBlock[]}` | 容器 | 见 F-MR-5 容器型规则 |
| `collapsible` | `{summary: string, content_blocks: ContentBlock[], default_open?: bool}` | 展开/折叠 | 容器,默认折叠 |
| `table` | `{columns: [{key, label}], rows: Array<Record<key, any>>, page_size?: number}` | 排序(列点击)、分页(可选) | 简单表格,不做公式 |

> `text` 不单独作为 renderer;`markdown` 即其实现,空文本走 `markdown` 渲染空字符串。

### F-MR-3 交互控件(14 种,MVP 必交付)

按"用户能做什么"分类。所有交互控件的 `data` 顶层必须包含 `action: string`(插件 handler 名)与 `args?: object`;部分含 `value_field` 标识回传字段名。

#### A. 文本/数字输入(3)
| type | data schema | 回传 |
|------|-------------|------|
| `input.text` | `{label, placeholder?, default?, required?, action, args?, value_field: "value"}` | `{value: string}` |
| `input.textarea` | 同上,加 `{rows?: number}` | `{value: string}` |
| `input.number` | `{label, min?, max?, step?, default?, action, args?, value_field}` | `{value: number}` |

#### B. 选择类(4)
| type | data schema | 回传 |
|------|-------------|------|
| `input.select` | `{label, options: [{label, value}], default?, action, args?, value_field}` | `{value: string}` |
| `input.radio` | `{label, options: [{label, value}], default?, action, args?, value_field}` | `{value: string}` |
| `input.checkbox` | `{label, options: [{label, value}], default?: string[], action, args?, value_field}` | `{value: string[]}` |
| `input.toggle` | `{label, default?: bool, action, args?, value_field}` | `{value: bool}` |

#### C. 时间(1)
| type | data schema | 回传 |
|------|-------------|------|
| `input.date` | `{label, mode: "date"\|"time"\|"datetime", default?, min?, max?, action, args?, value_field}` | `{value: string(ISO)}` |

#### D. 媒体上传(1)
| type | data schema | 回传 |
|------|-------------|------|
| `input.file` | `{label, accept?: string, multiple?: bool, max_size?: number, action, args?, value_field}` | `{files: [{id, name, mime, size}]}` |

#### E. 决策类(1)
| type | data schema | 回传 |
|------|-------------|------|
| `input.confirm` | `{message, confirm_label?, cancel_label?, destructive?: bool, action, args?}` | `{confirmed: bool}` |

#### F. 容器(1)
| type | data schema | 回传 |
|------|-------------|------|
| `input.form` | `{label, fields: ContentBlock[], submit_label?, cancel_label?, action, args?}` | `{values: Record<field_id, any>}` |

#### G. 轻反馈(不回传数据,只触发副作用,3)
| type | data schema | 副作用 |
|------|-------------|--------|
| `action.copy` | `{text: string, label?: string}` | 复制 text 到剪贴板 |
| `action.thumbs` | `{target_block_id: string, initial?: "up"\|"down"}` | 反馈点赞/点踩,只发事件不阻塞对话 |
| `action.regenerate` | `{label?, args?}` | 重新生成上一条 assistant 消息 |

### F-MR-4 消息接收方渲染规则
- F-MR-4.1 同一消息的多个 block 顺序渲染,块间距由 WebUI 主题决定
- F-MR-4.2 流式输出时,`markdown` 块按 token 增量更新;非 markdown 块在流结束时一次性追加
- F-MR-4.3 `code` / `table` / `card` 等容器内不支持流式(整体渲染)
- F-MR-4.4 失败/超时的 renderer 走降级:展示"⚠ 渲染失败: <type>" + 折叠的原始 data

### F-MR-5 容器型与嵌套规则
- F-MR-5.1 `card.body_blocks` 与 `card.actions` 可包含任何展示类 block(嵌套 card 也允许)
- F-MR-5.2 `card.actions` 中的元素**只允许** `action.*`(按钮类)与 `input.confirm`,不允许 `input.text` 等需要回填的控件(避免歧义)
- F-MR-5.3 `collapsible.content_blocks` 可包含任何展示类 block,**不可包含交互控件**
- F-MR-5.4 `input.form.fields` 是 flat 列表(每个 field 是一个独立的输入类 block,使用 `meta.id` 标识字段名)
- F-MR-5.5 嵌套深度上限 = **3 层**(M1 验证后可能放宽),超出走降级

### F-MR-6 未知 / 错误 Renderer 降级
- F-MR-6.1 未注册的 renderer:展示 `<未知组件: {type}>` 灰色块 + 原始 data 折叠(可点开查看)
- F-MR-6.2 已知 renderer 但 data schema 校验失败:同上降级 + 错误日志(前端 console + 后端结构化日志)
- F-MR-6.3 降级渲染不阻塞同消息其他 block 渲染
- F-MR-6.4 同一 renderer 连续 3 次降级 → 后端告警(便于发现 SDK 协议漂移)

### F-MR-7 交互回传(对接 Agent Loop)
- F-MR-7.1 用户操作交互控件 → WebUI 立即乐观更新(loading 态)→ POST `/api/sessions/{id}/blocks/{block_id}/interact` body = `{action, args, value}`
- F-MR-7.2 后端按 `action` 路由到对应插件 handler(命名空间 `plugin_id.action_name`)
- F-MR-7.3 handler 返回 `{blocks: ContentBlock[]}`;空数组表示"无后续消息";非空 → 续追加到当前消息流
- F-MR-7.4 handler 错误 → 展示错误态(retry 按钮),不污染上下文
- F-MR-7.5 `action.copy` / `action.thumbs` / `action.regenerate` 是"副作用型",不走 F-MR-7.1 的回传路径,只发事件到后端(无返回值)

### F-MR-8 安全与国际化
- F-MR-8.1 `markdown` 必须经 sanitization(MVP 用 DOMPurify 或等价),不允许 `<script>` / `<iframe>` / `on*` 属性
- F-MR-8.2 `code` 块高亮走"语法着色 + 转义",不 eval
- F-MR-8.3 所有图片 url 必须 HTTPS,本地路径经后端代理 + 鉴权
- F-MR-8.4 文件下载经后端鉴权 + mime 白名单(默认 `text/*` `image/*` `application/pdf` 可预览,其他仅下载)
- F-MR-8.5 renderer 名称空间:平台内置无前缀,插件带 `<plugin_id>.<renderer_name>` 前缀(详见 [ADR 0001](../adr/0001-namespace.md))
- F-MR-8.6 i18n 基线:`markdown` / `button` / 控件 label 字段支持 i18n key(`i18n:<key>`),未识别 key 原样展示;MVP 不强求所有插件走 i18n

### F-MR-9 UI 扩展性边界(新增)

> 明确"插件能对 UI 做什么 / 不能做什么"。MVP 锁定**只支持 renderer 挂件**。

- F-MR-9.1 MVP 只支持 **renderer 挂件模式**:插件通过 SDK 注册块级 UI(renderer),渲染在消息流内
- F-MR-9.2 **不允许**注册整页 / 整对话窗口 / 自定义路由——这些是 WebUI 主壳的责任,不放给插件(留 v1.4 评估)
- F-MR-9.3 插件**不能**替换 WebUI 主壳 / 主题 / 全局导航 / 侧边栏——只能"挂"内容到消息流
- F-MR-9.4 侧边栏 widget / 全局工具栏按钮等"挂件位":MVP **不开**,留 v1.4 评估

---

## 5. 非功能需求

- **性能**:1000 条消息、混合 21 种 renderer、首屏 P95 < 2s(本地压测);单 block 渲染 < 16ms
- **可观测**:每次交互回传记结构化日志 `{session_id, plugin_id, action, block_type, latency_ms, status}`;未知 renderer 走 warn 级
- **可测试**:每个 renderer 必须有 1)schema 单元测试 2)渲染快照测试 3)交互回传端到端测试
- **版本兼容**:renderer schema 演进走 semver;老 WebUI 遇到新 schema 字段不报错(忽略未知字段)
- **前端体积**:21 种内置 renderer 打包后增量 < 200KB gzipped

---

## 6. 接口契约(粗略,设计阶段细化)

### 6.1 消息传输(API)
```
GET  /api/sessions/{id}/messages          # 历史消息列表
POST /api/sessions/{id}/messages/stream   # 流式输出(SSE 或 WebSocket)
POST /api/sessions/{id}/blocks/{bid}/interact  # 交互回传
```

### 6.2 插件 SDK 注册接口(`platform.sdk`,Python)
```python
from platform.sdk import renderer

@renderer.register(
    name="my_plugin.weather_card",
    schema={
        "type": "object",
        "properties": {"city": {"type": "string"}, "temp": {"type": "number"}},
        "required": ["city", "temp"],
    },
    interactive=False,
)
class WeatherCardRenderer:
    def to_blocks(self, data: dict) -> list[dict]:
        # 服务端把内部数据转成 ContentBlock 列表
        return [{"type": "my_plugin.weather_card", "data": data}]
```

### 6.3 插件交互 Handler 接口
```python
from platform.sdk import handler

@handler.register(action="my_plugin.regenerate_weather")
async def regenerate_weather(session_ctx, block_id: str, args: dict) -> list[dict]:
    # 返回新的 ContentBlock 列表
    return [...]
```

### 6.4 WebUI Renderer Registry(前端)
```ts
// platform-web/renderers/registry.ts
import { markdownRenderer } from './markdown';
import { codeRenderer } from './code';
// ... 21 个内置 renderer

export const registry = new Map<string, Renderer>([
  ['markdown', markdownRenderer],
  ['code', codeRenderer],
  // ...
]);
```

### 6.5 插件自定义 Renderer(前端)
插件可同时提供前端 renderer 包(单独的 npm 包),由插件清单声明 `frontend_renderer: "my-plugin-renderer@1.0.0"`,WebUI 在加载插件时动态 import。

---

## 7. MVP 范围与非目标

### 7.1 v1.3 范围
- F-MR-1 至 F-MR-8 全部条目
- 21 种 renderer 全部交付(包括内置实现 + 降级 + 安全)
- 1 个参考插件(内置 `weather` demo)演示:markdown + table + button + form 组合
- 文档:插件开发者"如何注册 renderer"教程;WebUI 维护者"如何新增内置 renderer"指南

### 7.2 非目标(v1.3 不做,留待后续)
- 富文本编辑器(用户编辑消息时所见即所得)
- 实时协同(多人编辑同一消息)
- 拖拽排序 / 滑块 / 评分 / 地图选点 / 录音 等高级控件
- 跨插件 renderer 复用(weather 插件复用 code 插件的代码块渲染)— 留 v1.4
- renderer 主题/皮肤系统(MVP 用 WebUI 主题)
- 国际化词条平台(MVP 仅支持 i18n key,词条由插件自带)
- 服务端渲染(SSR)
- 移动端原生交互优化(响应式即可)

---

## 8. 决策状态

### 8.1 已确认(本 v1.3 锁定)
- ✅ 把"消息渲染"从 WebUI 硬编码解耦,改为插件可声明 renderer
- ✅ 消息信封:统一 `Message = {role, blocks[]}`,role 沿用 OpenAI 风格
- ✅ renderer 名称空间:反向 DNS 风格,平台内置无前缀,插件带 `<plugin_id>.` 前缀
- ✅ 21 种 renderer 最小集(7 展示 + 14 交互;含 3 轻反馈)
- ✅ 容器型(card / collapsible / form)纳入 003 v1.0;嵌套深度上限 3 层
- ✅ 未知 / 错误 renderer 走降级(不崩溃、有告警)
- ✅ 交互回传路径:WebUI → 后端 → 插件 handler → 续 block 列表
- ✅ markdown sanitization 强制(DOMPurify 或等价)
- ✅ 本地文件经后端代理 + 鉴权,不直接暴露文件系统
- ✅ i18n key 形式支持,但不强求所有插件接入
- ✅ UI 扩展性边界:MVP 只支持 renderer 挂件,不开放整页 / 整窗口 / 自定义路由 / 侧边栏 widget

### 8.2 留待设计阶段(对应设计 003-ui-components.md)
- 消息流传输具体协议(SSE vs WebSocket 选型,断线重连策略)— 关联设计 003 / 005
- 交互回传的鉴权与速率限制(防刷)— 关联设计 005 安全
- 插件前端 renderer 包的加载机制(动态 import / bundle 策略 / 版本校验)— 关联设计 003
- 跨插件 renderer 复用的命名与冲突解决(留 v1.4 后回看)
- 历史消息(`content: string`)迁移到新信封的兼容期策略
- 嵌套深度上限 3 是否合理,需实施后回归

### 8.3 与 001 的关系
- 001 §F3.2 现有表述"基础类型:文本框、复选框、按钮" → 003 v1.0 生效后,001 F3.2 增补"详见 003 §F-MR-2/F-MR-3"
- 001 §7.1 MVP "插件定义富交互组件(基础类型)" → 不变,但范围以 003 为准
- 001 §8.2 "富交互组件协议细节" → 由 003 锁定协议,设计阶段(对应 003-ui-components.md)落实技术细节
