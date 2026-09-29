# 技术设计 · Agent Harness 加固(016 · 对应需求 011)

- 文档版本:v0.1(草案,待评审)
- 日期:2026-09-29
- 流程阶段:阶段 2 · 设计
- 关联决策:ADR 0009(断线检查点)、ADR 0010(错误分类与轮次追踪)、ADR 0011(上下文压缩)

---

## 1. 总体架构

现状分层与本次加固落点:

```
┌─ API 层(api/chat.py)          ← H1:草稿消息渐进落库 + resume 端点
├─ 编排层(core/agent/loop.py)   ← H2:瘦身为编排器;H5:调用路径分流标记
├─ 执行层(executor/dispatch)    ← H2:新增 dispatch.py;H4:错误分类落位
├─ 上下文层(context.py,新增)  ← H3:历史构建与压缩
└─ 通道层(core/llm/*)           ← 已有端点级重试,基本不动
```

设计原则:不动 SDK 契约与插件接口;所有新行为可配置、可灰度、可回退;不新增基础设施。

## 2. H1 · 断线检查点与续跑

### 2.1 现状缺陷

`api/chat.py` 的 `event_stream` 仅在**流正常结束**时 `save_assistant_message`;
通用异常路径 rollback **整轮丢弃**(chat.py:313-315),用户侧表现为回复消失、
手动重发、重复计费。loop 内部多轮工具调用全部完成后才落库,断点信息为零。

### 2.2 设计(详见 ADR 0009)

**草稿消息 + 轮次边界 flush**:

1. 助手消息行在**首轮 LLM 调用前**创建(`is_draft=True`),后续每轮边界
   (发起下一次 LLM 调用前、每次工具执行后)将累计 text/blocks/usage flush 到该行;
2. 连接断开/异常时,已 flush 的草稿天然留存(每次 flush 即 commit);
3. 通用异常路径改为与用户取消一致:**保存 partial,不再 rollback 丢弃**;
4. 新端点 `POST /chat/sessions/{sid}/resume`:
   - 定位会话最后一个 `is_draft` 消息及其 `agent_round_trace` 记录;
   - 以「历史 + 草稿已完成内容 + 已完成工具调用结果」重建消息列表,
     仅对未完成的轮次重新发起 LLM 调用(已完成工具不重跑、不重复计费);
   - 流式补齐剩余内容,结束时将草稿行原地 finalize(`is_draft=False`);
   - SSE 事件携带 `resume_of: <message_id>`,前端**原位替换**草稿渲染,不追加新气泡;
5. 放弃续跑(用户不点重试):草稿保留为部分回答,历史一致可见;
   新一轮正常消息继续追加。

### 2.3 数据模型变更(alembic)

- `messages` 新增 `is_draft Boolean NOT NULL DEFAULT false`;
- 新表 `agent_round_trace`(ADR 0010):
  `id, session_id, message_id(FK messages), round, kind(chat/skill/tool),
  tool_path(native|text_fallback|none), tokens, error_kind(nullable),
  error_detail(nullable), created_at`。

## 3. H2 · 并发结构重构

### 3.1 模块拆分(loop.py 1192 行 → 职责单一)

| 模块 | 职责 | 来源 |
|---|---|---|
| `agent/loop.py` | 编排:轮次循环、事件产出、检查点 flush 协作 | 保留骨架,目标 ≤400 行 |
| `agent/dispatch.py`(新增) | 工具调用解析与路由:native tool_calls 流解析、文本兜底解析(现 `_extract_text_tool_calls` 等)、`_find_resource` 变体匹配 | 自 loop.py 迁出 |
| `agent/context.py`(新增) | 历史构建、token 计量、压缩(H3) | 新实现 |
| `agent/executor.py` | tool/skill 执行(已有) | 不动,错误分类接入 |
| `agent/bridge.py` | 端侧工具(已有) | 不动 |

### 3.2 轮询消除

现状:`skill_delta_queue`(0.05s)+ `progress_q`(0.1s)两处 `wait_for` 轮询,
是嵌套流静默失败与取消传播缺陷的温床。改为**统一的异步生成器合并**:

- 子调用(skill 嵌套流、端侧工具)以 `asyncio.Task` + `asyncio.Queue` 封装为
  `async generator`;主循环 `async for` 消费,`asyncio.CancelledError` 自然传播;
- 队列消费与任务完成用 `await queue.get()` 阻塞等待 + task done callback 投递
  结束哨兵,轮询间隔清零;
- 子调用失败以结构化错误事件进入合并流(H4 分类),禁止静默丢弃
  (20260928 断流修复的泛化)。

## 4. H3 · 上下文压缩(详见 ADR 0011)

`agent/context.py`:

1. **计量**:每轮结束后从 `done.usage` 累计会话 token( messages.tokens 已落库,
   补齐历史轮次估算);
2. **触发**:会话 token 估算 > 端点窗口 × `compaction_threshold`(默认 0.7,
   可配置,settings 注入)时触发;
3. **策略**:保留 system prompt + 最近 `keep_recent_turns`(默认 6)轮原文,
   更早轮次合并为**单条滚动摘要**(一次低温度 LLM 调用);摘要行以
   `MessageRole.summary` 固化在 messages 表,下次压缩**增量滚动**(旧摘要+新淘汰
   轮次 → 新摘要),避免重复摘要全量历史;
4. **可知情**:摘要行不渲染为聊天气泡,工作台"查看上下文摘要"入口按需展开;
   压缩事件(token before/after、轮次范围)落 `agent_round_trace.kind=compaction`;
5. **成本闸**:单会话摘要调用频率上限(默认 10 分钟内 1 次),避免反复触发。

## 5. H4 · 错误分类体系(详见 ADR 0010)

`agent/errors.py` 扩展:

| kind | 含义 | 处理策略 | 用户话术 |
|---|---|---|---|
| `transient` | 网络抖动/超时/429 | 通道层自动重试(预算:3 次指数退避) | 无感 |
| `checkpoint_resume` | 流中断可续跑 | 检查点保留 + resume 端点 | "连接中断,可从断点继续" |
| `tool_failure` | 工具执行失败 | 结果回填模型自纠(现状行为,显式化) | 无感(模型自纠) |
| `deploy_broken` | 部署态断线(impl 缺失等) | 自愈(ensure_resource_impl)→ 不行则明确报错 | "技能实现未加载,请联系开发者" |
| `contract` | 模型输出不合契约(工具调用解析失败等) | 有界重试 1 次 + 纠偏提示 | 无感 |
| `internal` | 平台 bug | 落日志 + 结构化错误事件 | "平台内部错误,已记录" |

每轮异常按类落 `agent_round_trace.error_kind`;SSE `error` 事件统一携带
`{code, kind, message, resumable}`;新增错误类型须先归入既有类并补策略声明。

## 6. H5 · 工具调用路径分流

1. `llm_endpoints` 新增 `supports_native_tools Boolean NOT NULL DEFAULT true`
   (alembic;存量端点默认 true,个别不支持的由管理员显式置 false);
2. `dispatch.py` 按端点能力选择解析路径:native → 文本兜底直接跳过;
   兜底路径仅在 `supports_native_tools=false` 时启用,每次触发落
   `agent_round_trace.tool_path=text_fallback`,触发面可统计、可收敛;
3. 文本兜底解析行为不变(不做语义改动),仅收口入口与可观测。

## 7. 分期实施与测试

| 期 | 内容 | 关键测试 |
|---|---|---|
| P1 | H1 检查点/续跑 + 异常路径 partial 落库 | 注入断流:草稿留存、resume 续跑、工具不重跑、tokens 不重复计费 |
| P2 | H4 错误分类 + trace 表 + H2 拆分与轮询消除 | 故障注入矩阵(子调用失败/session 失效/解析失败);loop.py ≤400 行 lint 约束 |
| P3 | H3 压缩 + H5 分流 | 50 轮会话 token 上界用例;压缩摘要保留早期约束用例;text_fallback 计数 |

每期独立交付、独立开关(`settings.harness_resume_enabled` 等),可一键回退。

## 8. 风险与回退

- **草稿消息与并发写**:单会话串行(现状即有会话锁),无新增竞争;
- **压缩质量**:摘要丢关键约束 → 摘要 prompt 固定包含"用户声明的约束与偏好逐条保留";
  验收用例集守护(需求 011 A3);
- **resume 幂等**:前端按 `resume_of` 原位替换,后端 finalize 原子更新,
  重复 resume 以 trace 记录的 round 游标去重;
- **整体回退**:各期独立 feature flag,关闭即回到现行为。
