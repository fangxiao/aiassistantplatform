# 003 · 消息渲染设计

- 文档版本:**v2.0(基于需求 003 重写)**
- 日期:2026-08-12
- 流程阶段:阶段 2 · 设计
- 对应需求:[003-message-rendering.md](../requirements/003-message-rendering.md) v1.0(定稿)
- 协同设计:[001-architecture](./001-architecture.md) / [004-data-model](./004-data-model.md) / [005-api-design](./005-api-design.md) / [006-plugin-spec](./006-plugin-spec.md)
- 引用 ADR:[0001-namespace](../adr/0001-namespace.md)

## 变更记录
- **v2.0(2026-08-12):基于需求 003 重写**。覆盖 21 种 renderer / 消息信封 `{role, blocks[]}` / 容器型与嵌套 / 未知 renderer 降级 / 交互回传路径 / 安全。**旧版"render_component 伪 tool"机制废弃**。
- v0.1(2026-08-11):初版草案,仅覆盖 5 种组件 + 伪 tool_call 机制。

---

## 1. 设计目标

把需求 003 锁定的 21 种 renderer 落到可实现的技术方案:

1. **消息信封替代伪 tool**:`Message = {role, blocks[]}` 成为消息的天然结构,LLM 不再需要 `render_component` 伪 tool——平台后端在流式输出时,把内部事件流转换为 ContentBlock 列表
2. **前端 registry 调度**:WebUI 维护内置 renderer registry,插件可动态注入自定义 renderer(对齐 ADR 0001 命名空间)
3. **交互回传走 HTTP POST**:WebUI → `/api/sessions/{id}/blocks/{bid}/interact` → 插件 handler → 续 block 列表(简单、RESTful、不引入双协议)
4. **降级是默认行为**:未知 / 出错 renderer 走降级组件,不崩溃
5. **NFR 可度量**:单 block 渲染 < 16ms;1000 条消息首屏 < 2s

## 2. 与需求 003 的对应

| 需求条款 | 本设计章节 |
|----------|------------|
| F-MR-1 消息信封协议 | §3 消息信封 |
| F-MR-2 展示类(7) | §5 展示类 renderer |
| F-MR-3 交互控件(14) | §6 交互控件 |
| F-MR-4 渲染规则 | §4 渲染调度 |
| F-MR-5 容器型与嵌套 | §7 容器型 |
| F-MR-6 降级 | §8 降级 |
| F-MR-7 交互回传 | §9 交互回传 |
| F-MR-8 安全 / 国际化 | §10 安全 |
| F-MR-9 UI 扩展性边界 | §11 边界 |
| §5 NFR | §12 性能与可观测 |
| §6 接口契约 | §13 数据结构 |

---

## 3. 消息信封协议(Message Envelope)

### 3.1 数据结构(统一)

```typescript
// frontend & backend 共享 schema
type Role = 'system' | 'user' | 'assistant' | 'tool';

interface Message {
  id: string;                  // uuid
  session_id: string;
  role: Role;
  blocks: ContentBlock[];      // 顺序渲染
  created_at: string;          // ISO 8601
  meta?: {                     // 消息级元信息
    parent_message_id?: string; // 多轮关联
    regenerate_of?: string;     // regenerate 来源
  };
}

interface ContentBlock {
  type: string;                // renderer name(详见 ADR 0001)
  data: Record<string, any>;   // renderer-specific
  meta?: {                     // 块级元信息
    id?: string;               // 交互回传定位
    group?: string;            // 逻辑分组
  };
}
```

**关键点**:
- `Message.content: string` 字段**废弃**(旧版使用),新消息只用 `blocks[]`
- 兼容模式:读取历史 `content` 时,前端按 `{type: "markdown", data: {text: content}}` 转换(后端不强制迁移,见 §3.4)

### 3.2 ContentBlock 分类

| 分类 | renderer type 命名 | 来源 |
|------|---------------------|------|
| 展示类 | `markdown` / `code` / `image` / `file` / `card` / `collapsible` / `table` | 平台内置 |
| 输入类 | `input.text` / `input.textarea` / `input.number` / `input.select` / `input.radio` / `input.checkbox` / `input.toggle` / `input.date` / `input.file` / `input.confirm` / `input.form` | 平台内置 |
| 轻反馈 | `action.copy` / `action.thumbs` / `action.regenerate` | 平台内置 |
| 容器型 | `card` / `collapsible` / `input.form` | (同上,跨分类) |
| **插件自定义** | `<plugin_id>.<renderer_name>`(对齐 ADR 0001) | 插件注册 |

### 3.3 流式分块策略

LLM 流式输出 token 时,后端需要把"delta token"转换为"block 增量"——这是与 005-api-design 协同的关键。

| 块类型 | 流式行为 | 理由 |
|--------|----------|------|
| `markdown` | 按 token 增量更新最后一个 markdown block 的 `data.text` | 文本可增量 |
| `code` / `image` / `file` / `table` | **不在流式过程中出现**;LLM 流结束后一次性追加(整体渲染) | 结构化内容需要完整 |
| `card` / `collapsible` | 同上 | 容器型 |
| 交互控件 | 跟随 LLM 工具调用结果,流结束追加 | 触发条件明确 |
| `action.*` | 同上 | 副作用型 |

**后端转换层**(关键设计):

```
[LLM 流式 token + tool_call 事件]
        ↓ 事件聚合
[block 边界检测:何时开新 block / 关闭当前 block]
        ↓
[SSE 事件:delta(增量) / block_meta(开新块) / interact(交互事件) / done / error]
        ↓
[WebUI 按事件类型 dispatch 到 registry]
```

**block 边界检测规则**(后端):
- LLM 进入新 function_call 阶段 → 关闭当前 markdown block,开新 `code` / `tool_result` 块
- LLM `render_*` 旧机制已废弃;新机制是:agent 内部用特殊 tool_call `output_block({type, data})` 显式声明"以下是一个 ContentBlock"——这是后端协议层的扩展,LLM 不感知,平台拦截后转为 SSE `block_meta` 事件

> **为什么不让 LLM 直接产 ContentBlock JSON**:LLM 在 function-calling 里直接输出 ContentBlock 会有几类问题(类型错误、嵌套不当、安全风险)。中间加一个 `output_block` 拦截层,后端做 schema 校验 + 嵌套深度检查 + 降级,LLM 仍然走标准 function-calling。

### 3.4 兼容模式(历史 `content: string`)

```typescript
// 前端读取历史消息
if (msg.blocks && msg.blocks.length > 0) {
  return msg.blocks;  // 新格式
}
// 旧格式回退
if (msg.content) {
  return [{ type: 'markdown', data: { text: msg.content } }];
}
return [];  // 空消息
```

**后端行为**:新生成的消息一律写 `blocks[]`,不写 `content`。读取时优先用 `blocks`,缺失则回退 `content` 字段(只读不改)。

---

## 4. 渲染调度(WebUI 端)

### 4.1 Renderer Registry

```typescript
// platform-web/renderers/registry.ts
type Renderer = React.ComponentType<{ data: any; meta?: any; onInteract?: (action: string, value: any) => void }>;

class RendererRegistry {
  private map = new Map<string, Renderer>();

  register(name: string, component: Renderer) {
    if (this.map.has(name) && !name.startsWith('plugin.')) {
      // 平台内置名不可被插件覆盖
      throw new Error(`Renderer "${name}" is a reserved platform renderer`);
    }
    this.map.set(name, component);
  }

  resolve(name: string): Renderer {
    return this.map.get(name) ?? this.map.get('__fallback__')!;
  }

  list(): string[] {
    return Array.from(this.map.keys());
  }
}

export const registry = new RendererRegistry();
// 21 种内置 renderer 全部 register(见 §5 / §6)
```

### 4.2 块级渲染器(BlockRenderer)

```typescript
// platform-web/renderers/BlockRenderer.tsx
export function BlockRenderer({ block, onInteract }: { block: ContentBlock; onInteract: ... }) {
  const Component = registry.resolve(block.type);
  return (
    <ErrorBoundary fallback={<FallbackRenderer block={block} />}>
      <Component data={block.data} meta={block.meta} onInteract={onInteract} />
    </ErrorBoundary>
  );
}
```

**关键点**:
- `ErrorBoundary` 捕获渲染错误,降级到 `FallbackRenderer`(详见 §8)
- 未注册 renderer(`registry.resolve` 返回 `__fallback__`)直接走降级
- `__fallback__` 默认实现:展示 `<未知组件: {type}>` + 原始 data 折叠

### 4.3 容器型递归渲染

容器型 renderer(`card` / `collapsible` / `input.form`)的 `data` 包含 `body_blocks` / `content_blocks` / `fields` 数组——**子块也走 `BlockRenderer` 递归渲染**:

```typescript
// card renderer
function CardRenderer({ data, meta, onInteract }) {
  return (
    <div className="card">
      {data.title && <div className="card-title">{data.title}</div>}
      <div className="card-body">
        {data.body_blocks?.map((b, i) => <BlockRenderer key={i} block={b} onInteract={onInteract} />)}
      </div>
      {data.actions && <div className="card-actions">{...}</div>}
    </div>
  );
}
```

**深度检测**(详见 §7.3):在 `BlockRenderer` 入口处读 `React.useContext(NestingContext)`,超 3 层直接渲染降级组件,不递归。

---

## 5. 展示类 Renderer(7 种,实现要点)

| type | 关键依赖 / 库 | props 要点 | 边界 |
|------|---------------|-----------|------|
| `markdown` | `react-markdown` + `remark-gfm` + `rehype-sanitize` | `data.text: string` | sanitizer 配置详见 §10.1 |
| `code` | `prismjs`(语法高亮)+ 自实现 `copy` 按钮 | `data.lang`, `data.source`, `data.filename?` | lang 不识别时降级纯文本 |
| `image` | `<img loading="lazy">` + 自实现 preview modal | `data.url`(HTTPS 强制), `data.alt?` | URL 校验失败 → 降级(图标 + URL) |
| `file` | 自实现 icon + size 格式化 | `data.name`, `data.url`, `data.mime`, `data.size` | preview 条件 = mime 在白名单 |
| `card` | 自实现 + 递归 BlockRenderer | `data.title?`, `data.body_blocks[]`, `data.actions[]` | actions 只允许 action.* 与 input.confirm |
| `collapsible` | 自实现 + 状态管理 | `data.summary`, `data.content_blocks[]`, `data.default_open?` | 不可含交互控件 |
| `table` | 自实现 + 简单排序 | `data.columns[]`, `data.rows[]`, `data.page_size?` | 列点击排序;不分页可走 page_size 客户端 |

**库选型理由**:
- `react-markdown`:React 原生,组件化,生态最大
- `rehype-sanitize`:与 DOMPurify 等价的 markdown sanitization 库
- `prismjs`:轻量,主题多,bundle 可控
- (备选)Shiki:VS Code 同款,质量更高但 bundle 大

---

## 6. 交互控件(14 种,实现要点)

### 6.1 通用 props

所有交互控件的 `data` 顶层结构:

```typescript
interface InteractiveData {
  // 控件自身字段(text / options / default 等)
  [key: string]: any;
  // 通用字段
  action: string;              // 插件 handler 名(命名: plugin_id.action_name)
  args?: Record<string, any>;  // 传给 handler 的固定参数
  value_field?: string;        // 回传字段名(默认 'value')
}
```

### 6.2 列表

| type | 库 / 实现 | 关键回传 |
|------|-----------|----------|
| `input.text` | `<input type="text">` | `{value: string}` |
| `input.textarea` | `<textarea>` | `{value: string}` |
| `input.number` | `<input type="number">` | `{value: number}` |
| `input.select` | `<select>` | `{value: string}` |
| `input.radio` | 自实现(受控组件) | `{value: string}` |
| `input.checkbox` | 自实现(多选) | `{value: string[]}` |
| `input.toggle` | 自实现(switch) | `{value: boolean}` |
| `input.date` | 原生 `<input type="date|time|datetime-local">` | `{value: string(ISO)}` |
| `input.file` | `<input type="file">` + 上传到后端 | `{files: [{id, name, mime, size}]}` |
| `input.confirm` | 自实现(确认/取消按钮) | `{confirmed: boolean}` |
| `input.form` | 组合其他 input 控件 | `{values: Record<field_id, any>}` |
| `action.copy` | `navigator.clipboard.writeText` | (无回传) |
| `action.thumbs` | 自实现(👍/👎) | (仅发事件,无回传) |
| `action.regenerate` | 触发 SSE 重发 | (仅发事件,无回传) |

### 6.3 交互态管理

- **简单控件**(text/select/checkbox/toggle):`React.useState` 受控
- **复杂表单**(`input.form`):`react-hook-form` 或自实现(用 `useReducer` 聚合多字段),提交时按 `fields[].meta.id` 拼装 `values` 对象
- **日期/时间**:MVP 用原生 input,后续考虑 date-fns 格式化
- **文件上传**:上传到 `/api/files`(POST multipart),返回 `id` 拼进 `files[]`

### 6.4 提交即回传

用户点提交(确认/完成/上传完成)→ 调 `onInteract(action, value)` → 走 §9 交互回传路径。

---

## 7. 容器型与嵌套

### 7.1 容器型清单

| 容器 | data 结构 | 嵌套规则 |
|------|-----------|----------|
| `card` | `{title?, body_blocks: ContentBlock[], actions: ContentBlock[]}` | body 可含展示类+交互控件;actions 只允许 action.* + input.confirm |
| `collapsible` | `{summary, content_blocks: ContentBlock[], default_open?}` | content **只允许展示类**,不可含交互控件 |
| `input.form` | `{label, fields: ContentBlock[], submit_label?}` | fields 是 flat 输入控件列表 |

### 7.2 嵌套深度上限 = 3

需求 003 §F-MR-5.5 锁定。算法:

```typescript
// platform-web/renderers/BlockRenderer.tsx
const NestingContext = React.createContext(0);

export function BlockRenderer({ block, onInteract }: Props) {
  const depth = React.useContext(NestingContext);

  // 容器型:深度 +1
  const isContainer = ['card', 'collapsible', 'input.form'].includes(block.type);
  const childDepth = isContainer ? depth + 1 : depth;

  // 超深度降级
  if (depth > 3) {
    return <FallbackRenderer block={block} reason="nested-too-deep" />;
  }

  return (
    <NestingContext.Provider value={childDepth}>
      {/* 实际渲染 */}
    </NestingContext.Provider>
  );
}
```

### 7.3 嵌套规则执行位置

**后端**:LLM 输出的 block 在落库前做静态校验(深度 + 容器规则),违规走降级或拒绝

**前端**:BlockRenderer 递归时做兜底校验(防止历史数据 / 跨版本数据违反)

---

## 8. 降级策略

### 8.1 降级触发条件

| 触发 | 降级组件 | 日志级别 |
|------|----------|----------|
| 未注册 renderer | `<未知组件: {type}>` 灰色块 + 原始 data 折叠 | warn |
| 已注册但 schema 校验失败 | 同上 + `⚠ schema error` | warn |
| 渲染时抛异常(ErrorBoundary 触发) | 同上 + 错误信息折叠 | error |
| 嵌套深度 > 3 | 容器内降级为"原始 data + 警告" | warn |
| 容器内嵌了违规子类型(collapsible 里有 input) | 该子块降级 + 容器正常渲染 | warn |

### 8.2 降级组件实现

```typescript
// platform-web/renderers/FallbackRenderer.tsx
export function FallbackRenderer({ block, reason }: { block: ContentBlock; reason?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="renderer-fallback">
      <div className="fallback-header" onClick={() => setOpen(!open)}>
        ⚠ 渲染失败:{block.type} {reason && `(${reason})`}
      </div>
      {open && <pre className="fallback-data">{JSON.stringify(block.data, null, 2)}</pre>}
    </div>
  );
}
```

### 8.3 告警阈值

需求 003 §F-MR-6.4:同一 renderer 连续 3 次降级 → 后端告警。后端实现:

```python
# platform/observability/alerts.py
fallback_counter: dict[str, int] = {}

def record_fallback(renderer_name: str):
    fallback_counter[renderer_name] = fallback_counter.get(renderer_name, 0) + 1
    if fallback_counter[renderer_name] >= 3:
        alert(f"renderer {renderer_name} 连续降级 {fallback_counter[renderer_name]} 次")
        fallback_counter[renderer_name] = 0  # 重置
```

---

## 9. 交互回传(对接 Agent Loop)

### 9.1 API 端点

```
POST /api/sessions/{session_id}/blocks/{block_id}/interact
Authorization: Bearer <JWT>
Content-Type: application/json

Request:
{
  "action": "my_plugin.submit_form",
  "args": { ... },           // 可选,覆盖 block data 中的 args
  "value": { ... }           // 用户操作产生的值(由 value_field 决定)
}

Response(200):
{
  "blocks": ContentBlock[]   // handler 返回的续 block 列表
}

Response(200,空):
{
  "blocks": []
}

Response(4xx):
{
  "error": { "code": "...", "message": "..." }
}
```

**注意**:005-api-design.md §4 旧版用的是 `/api/chat/sessions/{sid}/components/{cid}/submit`,**需同步更新为新路径**(见 §14 协同清单)。

### 9.2 后端处理流程

```
[WebUI POST /interact]
    ↓
[FastAPI handler:解析 session_id / block_id / body]
    ↓
[从 message.blocks[bid] 读 action 字段]
    ↓
[按命名空间 plugin_id.action_name 路由到插件 handler]
    ↓
[plugin.handler.execute(session_ctx, block_id, args, value)]
    ↓
[handler 返回 ContentBlock[]]
    ↓
[响应 WebUI;新 block 追加到 assistant 消息流]
```

### 9.3 错误处理

| 场景 | 行为 |
|------|------|
| handler 抛异常 | 返回 500 + 结构化错误,WebUI 展示错误态 + retry 按钮;**不污染上下文**(F-MR-7.4) |
| handler 超时(> 30s) | 返回 504,WebUI 展示超时态 |
| handler 返回空数组 | 200 OK,WebUI 不追加内容,对话结束当前轮 |
| 未知 action | 404 + "action not found"(可能插件已卸载) |
| 用户未登录 / 会话失效 | 401(由 FastAPI 依赖注入统一处理) |

### 9.4 副作用型 action 的事件流

`action.copy` / `action.thumbs` / `action.regenerate` 不走 §9.1 的回传路径:

| action | 后端处理 |
|--------|----------|
| `action.copy` | 不发请求(纯前端 clipboard API) |
| `action.thumbs` | `POST /api/sessions/{sid}/events` `{kind: "thumbs", target_block_id, value}`(只记日志/反馈,不阻塞对话) |
| `action.regenerate` | `POST /api/sessions/{sid}/messages/regenerate` 触发重新生成上一条 assistant 消息(走流式 SSE) |

---

## 10. 安全

### 10.1 markdown sanitization

```typescript
// react-markdown 配置
<ReactMarkdown
  remarkPlugins={[remarkGfm]}
  rehypePlugins={[[rehypeSanitize, {
    // 允许的标签 / 属性白名单
    tagNames: ['h1','h2','h3','h4','h5','h6','p','a','ul','ol','li','code','pre','blockquote','table','thead','tbody','tr','th','td','strong','em','br','hr','img'],
    attributes: {
      a: ['href', 'title', 'target', 'rel'],
      img: ['src', 'alt', 'title', 'width', 'height'],
      code: ['className'],  // 用于语法高亮
    },
    protocols: {
      href: ['http', 'https', 'mailto'],
      src: ['https'],
    },
  }]]}
/>
```

**禁止**:`<script>` / `<iframe>` / `<object>` / `<embed>` / `on*` 事件属性 / `javascript:` 协议

### 10.2 图片 / 文件 URL 强制

- 图片:`https://` 协议;本地路径经 `/api/files/{id}` 代理(后端校验 session 归属)
- 文件下载:经后端 `/api/files/{id}/download` 代理,mime 在白名单(`text/*` `image/*` `application/pdf` 可预览,其他仅下载)
- 代理层:统一鉴权 + 速率限制 + size 限制

### 10.3 renderer 命名空间隔离

对齐 [ADR 0001](../adr/0001-namespace.md):
- 平台内置 renderer:`markdown` / `code` / ...(保留名,插件不可注册同名)
- 插件 renderer:`<plugin_id>.<renderer_name>`(强制前缀,否则拒绝注册)
- Registry 注册时校验:已存在的内置名 → 抛错

### 10.4 i18n

`markdown` / `button` label 字段支持 i18n key:`i18n:<key>` → 走前端 i18n 库;未识别 key 原样展示。MVP 不强求所有插件走 i18n。

---

## 11. UI 扩展性边界

对齐需求 003 §F-MR-9:

| 允许 | 禁止 |
|------|------|
| 注册块级 renderer | 注册整页 / 整对话窗口 / 自定义路由 |
| 渲染到消息流内 | 替换 WebUI 主壳 / 主题 / 全局导航 |
|  | 注册侧边栏 widget(MVP 不开) |
|  | 注册全局工具栏按钮(MVP 不开) |

**实现侧**:WebUI 主壳代码**不**暴露"注册整页"的 API 表面;插件 SDK 只导出 `renderer.register` 函数,没有"页面注册"接口。

---

## 12. 性能与可观测

### 12.1 性能目标

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| 单 block 渲染 | < 16ms | React Profiler |
| 1000 条消息混合 21 种 renderer 首屏 | P95 < 2s | Lighthouse / 自定义 perf trace |
| 流式首字延迟 | 取决于 LLM 端点 | SSE `token` 事件时间 |
| 21 种内置 renderer 增量 bundle | < 200KB gzipped | webpack-bundle-analyzer |

### 12.2 性能策略

- **memoization**:`BlockRenderer` 用 `React.memo` + props 浅比较
- **图片懒加载**:`<img loading="lazy">`
- **长列表**:1000+ 条消息时启用虚拟滚动(`react-window` / `react-virtuoso`)
- **代码高亮懒加载**:Prism 语言模块按需动态 import
- **流式 markdown 节流**:token 增量 update 用 `requestAnimationFrame` 节流(避免每 token 触发重渲染)

### 12.3 可观测

**结构化日志**(每次交互回传):
```json
{
  "event": "block_interact",
  "session_id": "...",
  "plugin_id": "...",
  "action": "...",
  "block_type": "...",
  "latency_ms": 123,
  "status": "ok|error"
}
```

**指标**(Prometheus):
- `block_render_total{renderer, status}`(Counter)
- `block_render_duration_ms{renderer}`(Histogram)
- `block_fallback_total{renderer, reason}`(Counter)
- `block_interact_total{plugin_id, action, status}`(Counter)
- `block_interact_duration_ms{plugin_id, action}`(Histogram)

---

## 13. 数据结构(Pydantic / TypeScript)

### 13.1 后端 Pydantic

```python
# platform/schemas/message.py
from pydantic import BaseModel, Field
from typing import Literal, Any

Role = Literal['system', 'user', 'assistant', 'tool']

class BlockMeta(BaseModel):
    id: str | None = None
    group: str | None = None

class ContentBlock(BaseModel):
    type: str = Field(..., description="renderer name (ADR 0001)")
    data: dict[str, Any]
    meta: BlockMeta | None = None

class Message(BaseModel):
    id: str
    session_id: str
    role: Role
    blocks: list[ContentBlock]
    created_at: str
    meta: dict[str, Any] | None = None
```

### 13.2 前端 TypeScript

```typescript
// platform-web/types/message.ts(对应 §3.1)
export type Role = 'system' | 'user' | 'assistant' | 'tool';

export interface BlockMeta {
  id?: string;
  group?: string;
}

export interface ContentBlock {
  type: string;
  data: Record<string, any>;
  meta?: BlockMeta;
}

export interface Message {
  id: string;
  session_id: string;
  role: Role;
  blocks: ContentBlock[];
  created_at: string;
  meta?: Record<string, any>;
}
```

### 13.3 持久化(对齐 004-data-model)

```sql
-- 004 messages 表扩字段
ALTER TABLE messages ADD COLUMN blocks jsonb;  -- 新格式(优先)
-- content 字段保留(历史兼容)
```

---

## 14. 协同清单(与其他设计文档)

| 其他设计 | 需要同步的内容 |
|----------|----------------|
| **001-architecture** | §1.1 架构图中,API 层需要标"消息传输: SSE / 交互回传: HTTP POST" |
| **004-data-model** | §2 messages 表加 `blocks jsonb` 字段(§13.3) |
| **005-api-design** | §4 对话 API 改造:① 路径从 `/chat/sessions/{sid}/components/{cid}/submit` 改为 `/sessions/{sid}/blocks/{bid}/interact`;② SSE 事件类型从 `token/tool_call/component/done/error` 扩展为 `delta/block_meta/interact_req/interact_resp/done/error`;③ 移除 `component` 事件类型(block_meta 取代) |
| **006-plugin-spec** | §2 plugin.yaml 中 `ui_components` 段改为 `renderers`,声明自定义 renderer 的前端包路径(如 `frontend_renderer: "my-plugin-renderer@1.0.0"`) |

---

## 15. 决策状态

### 15.1 已确认(本 v2.0 锁定)
- ✅ 消息信封 `Message = {role, blocks[]}` 替代旧版 `content: string`
- ✅ 旧版 `render_component` 伪 tool_call 机制**废弃**,由后端 `output_block` 拦截层取代
- ✅ 21 种 renderer 最小集(7 展示 + 14 交互;含 3 轻反馈)
- ✅ 命名空间:平台内置无前缀,插件带 `plugin_id.`,详见 ADR 0001
- ✅ 容器型(card / collapsible / form)深度上限 3 层
- ✅ 未知 / 错误 renderer 走降级,连续 3 次告警
- ✅ 交互回传:WebUI → POST `/blocks/{bid}/interact` → 插件 handler
- ✅ 副作用型 action 不走回传路径(各自独立事件)
- ✅ markdown sanitization 强制(rehype-sanitize)
- ✅ 本地文件经后端代理 + 鉴权
- ✅ i18n key 形式支持,不强制
- ✅ UI 扩展性边界:MVP 只支持 renderer 挂件
- ✅ SSE 事件类型扩展:`delta / block_meta / interact_resp / done / error`

### 15.2 留待后续版本
- 长列表虚拟滚动:1000+ 条消息时启用,先做普通渲染观察瓶颈
- 拖拽 / 滑块 / 评分 / 地图选点 / 录音等高级控件:v1.4+
- 跨插件 renderer 复用:v1.4+(需考虑命名空间扩展)
- 主题 / 皮肤系统
- 移动端原生交互优化
- SSR(服务端渲染)
- 插件前端 renderer 包的版本校验 / bundle 策略细节化

### 15.3 与需求 003 的关系
- 需求 003 §F-MR-x 全部由本设计落实
- 需求 003 §8.1 已确认决策全部实现
- 需求 003 §8.2 留待设计条目已在本 §15.2 列出
