# 任务拆解 · 端云协同 Browser Agent (RFC-2026-001 落地)

- 文档版本:v0.1
- 日期:2026-08-25
- 流程阶段:阶段 3 · 任务拆解(增量)
- 依据:[RFC-2026-001-browser-agent-capabilities](../design/RFC-2026-001-browser-agent-capabilities.md)
- 里程碑命名:M11 · 端云协同

---

## 1. 概述

基于 RFC-2026-001,拆解为 M11(端云协同)里程碑。核心是 **RFC-0(交互回填续跑 agent)**,这是端云协同的地基(有无问题);RFC-1/3/4 为平台公共能力沉淀;机制 B 与 RFC-2 为机制改进/优化项。

优先级:
- **P0**:RFC-0 交互回填续跑(端云闭环地基)
- **P1**:RFC-1 html_cleaner / RFC-3 browser.* 控件 / RFC-4 cross_document_compare
- **P2**:机制 B depends_on 可选依赖 / RFC-2 WebSocket 网关

---

## 2. 依赖关系总览

```
M11(端云协同)
├─ RFC-0 (T11.1-T11.6) 交互回填续跑 agent ──── P0,地基
│    ├─ T11.1 端侧工具登记与路由 ────────── 需 M2 注册表 / M5 loop
│    ├─ T11.2 await_external 输出块类型 ──── 需 M7 output_block
│    ├─ T11.3 interact handler 升级 ──────── 需 M7 interact
│    ├─ T11.4 loop 暂停/续跑状态机 ───────── 需 M5 loop / T11.2
│    ├─ T11.5 协议契约落地(TOOL_CALL/TOOL_RESULT) ─ 需 T11.1-T11.4
│    └─ T11.6 测试 + 端到端联调 ──────────── 需 T11.5
├─ RFC-1 (T11.7) tool:html_cleaner ──────── P1,独立
├─ RFC-3 (T11.8) browser.* ContentBlocks ── P1,依赖 RFC-0
├─ RFC-4 (T11.9) skill:cross_document_compare ─ P1,独立
├─ 机制B (T11.10) depends_on 可选依赖 ───── P2,独立
└─ RFC-2 (T11.11) WebSocket 网关 ────────── P2,优化项
```

---

## 3. 里程碑与任务

### M11 · 端云协同(P0 核心 = RFC-0)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T11.1 | **端侧工具登记与路由**:注册表模型扩展,支持 `impl_kind=endpoint` 资源(非本地实现,走通道路由);agent loop `execute()` 分支识别端侧工具不下发本地执行 | T2.2, T5.4 | P0 |
| T11.2 | **`await_external` 输出块类型**:agent 产出 `output_block({type:"await_external", data:{action, ...}})`;SSE 流按 `block_meta` 下发 | T7.2 | P0 |
| T11.3 | **interact handler 升级**:`handle_interaction` 识别等待中的 `await_external` 块 → 注入结果到对话上下文 → 触发续跑(而非返回静态确认) | T7.3, T11.2 | P0 |
| T11.4 | **loop 暂停/续跑状态机**:`loop.py` 引入"等待外部"状态;LLM 产出 `await_external` 后暂停,interact 到达后注入结果恢复推理并继续产出 SSE | T5.4, T11.2 | P0 |
| T11.5 | **协议契约落地**:端云标准通信协议(多 Tab 上报 / TOOL_CALL 下发 / TOOL_RESULT 回传);下行走 SSE + 上行走 interact(POC),预留 WebSocket 承载位 | T11.1-T11.4 | P0 |
| T11.6 | **测试 + 端到端联调**:单测(loop 暂停/续跑、interact 回填)+ 集成测试(模拟端侧工具执行回填续跑闭环) | T11.5 | P0 |

> **T11.1 详细设计**
> - 注册表 `SkillTool` 增加 `impl_kind` 字段(默认 `local`,新增 `endpoint`)
> - 端侧工具登记:`tool:browser.read_page@^1.0` 等,`impl_path` 指向端侧动作协议名,不加载本地代码
> - `build_tools`(loop.py)仍映射为 LLM function(LLM 可见),但 `execute()` 命中 `endpoint` 时走 `route_to_endpoint()`
> - 通道路由先内聚为 `core/agent/bridge.py`(下行 emit + 上行等待),后续 WebSocket 网关接入同一接口

> **T11.4 状态机示意**
> ```
> LLM 推理 → 产出 await_external 块 → 暂停(等待 interact)
>                                  ↓
>              interact 到达 → 注入结果 → 恢复推理 → 继续产出 SSE
> ```

---

### RFC-1 · tool:html_cleaner(P1)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T11.7 | **内置 `tool:html_cleaner@^1.0`**:HTML/DOM 去噪 + Markdown 转换 + 表格结构化提取(Readability/Trafilatura 算法);注册表登记 + 实现 + 测试 | T2.3 | P1 |

> 输入 `html_content: string, extract_tables: bool`;输出 `title / cleaned_markdown / tables_json / metadata`(见 RFC-2026-001 §RFC-1)。

---

### RFC-3 · browser.* 端侧 ContentBlocks(P1,依赖 RFC-0)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T11.8 | **端侧执行类控件**:新增 `browser.highlight` / `browser.scroll_to` / `browser.open_tab` / `browser.fill_form`(UI 指令类)+ `browser.action.readPage` / `extractData` / `clickElement`(能力执行类);前端 renderer 注册 + 能力目录更新 | T11.6 | P1 |

> 能力执行类(B)依赖 RFC-0 的回填续跑能力,否则只能做单向 UI 指令语义。

---

### RFC-4 · skill:cross_document_compare(P1)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T11.9 | **内置 `skill:cross_document_compare@^1.0`**:多实体/多维度横向比对矩阵抽取(基于现有 skill 组合);注册表登记 + 实现 + 测试 | T2.3 | P1 |

> 输入 `entities: list[dict], dimensions: list[string]`;输出 `comparison_matrix / summary_markdown`(见 RFC-2026-001 §RFC-4)。

---

### 机制 B · depends_on 可选依赖/回退(P2)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T11.10 ✅ | **`depends_on` 可选依赖语义**(2026-09 完成):可选语法 `tool:html_cleaner@^1.0?`;`parse_dependency` 识别 `?`;必选依赖仅公共资源(builtin/shared)可满足,可选缺失不阻断部署;`resolve()` 运行时"公共优先、私有回退";本地回退实现与公共资源同 id+version 撞键拒绝;CLI validate 兼容 | T2.2, T4.2 | P2 |

---

### RFC-2 · WebSocket 网关(P2,优化项)

| ID | 任务 | 依赖 | 优先级 | 状态 |
|----|------|------|--------|------|
| T11.11 ✅ | **`/api/browser/tunnel` WebSocket 网关**:长连接 + 身份认证/配对 + 心跳保活 + 活跃 Tab 广播;对接 RFC-0 的 `core/agent/bridge.py` 通道路由。2026-09 生产化加固:TOOL_RESULT/PROGRESS 按 user 归属校验(防跨用户伪造)、device_id 配对识别、修复心跳窗口消息被丢弃导致的假性超时、非法 JSON 不杀连接、`GET /api/browser/sessions` 连接自省 | T11.6 | P2 | ✅ POC→生产化 |

> 降级为优化项:WebSocket 只解决延迟,不解决能力;RFC-0 的 SSE 下行 + interact 上行已能闭环(见 RFC-2026-001 §RFC-0 论证)。

**T11.11 实现要点(2026-08-26)**:
- 新增 `agentplatform/core/agent/bridge.py`:`BrowserBridge` 进程内单例通道路由(下行 `TOOL_CALL` emit + 上行 `TOOL_RESULT` await,基于 `asyncio.Future`),支持连接注册/注销、活跃 Tab 记录与同用户广播、连接中断时在途调用立即失败。
- 新增 `agentplatform/api/browser.py`:`/api/browser/tunnel` WebSocket 端点。**身份认证**:`?token=<JWT>` 查询参数(浏览器无法设置 header),复用 `decode_access_token`;**心跳保活**:应用层 PING/PONG + 超时断开;**活跃 Tab 广播**:`TAB_UPDATE` 记录并广播给同用户其他连接。
- `core/agent/loop.py` 端侧工具分支改造:**浏览器已连接 → 经 bridge `route_to_endpoint` 等待结果回填并继续推理**;未连接 → 降级为既有 `await_external` SSE + 暂停(向后兼容)。`stream_agent`/`run_agent` 新增 `owner_id` 参数,由 `agent_stream_for_session` 透传会话用户。
- 配置:`browser_tunnel_heartbeat`(30s)/ `browser_tunnel_timeout`(15s)/ `browser_route_timeout`(120s)。
- 已知限制:bridge 为进程内存单例(多 worker 各实例独立,跨 worker 路由需 Redis pub/sub,留待规模化阶段);**配对**复用用户 JWT + device_id 多设备识别,专用短时浏览器令牌留作后续;`endpoint:` 前缀约定代替 T11.1 建议的 `impl_kind` 列(未做迁移)。

---

## 4. 建议实施顺序

**Phase A · 端云地基(P0):**
```
T11.1 端侧工具登记路由 → T11.2 await_external 块 → T11.4 loop 暂停/续跑
→ T11.3 interact handler 升级 → T11.5 协议契约 → T11.6 测试联调
```

**Phase B · 平台公共能力(P1):**
```
T11.7 html_cleaner → T11.8 browser.* 控件(依赖 A)→ T11.9 cross_document_compare
```

**Phase C · 机制改进与优化(P2):**
```
T11.10 可选依赖 → T11.11 WebSocket 网关
```

---

## 5. 说明
- **RFC-0 是端云协同的地基**:WebSocket 网关(T11.11)只解决延迟,回填续跑(T11.1-T11.6)解决有无,必须先行
- 端侧工具执行体在插件(Chrome extension),但 schema 在平台注册表——LLM 才能 function calling 选择它们
- 协议契约先以 SSE(下行)+ interact(上行)落地 POC,WebSocket 网关作为通道路由承载后置接入,接口收敛于 `core/agent/bridge.py`
