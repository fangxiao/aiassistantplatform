# 0002 · 自研 Agent Loop(不引入重量级框架)

- 状态:**Accepted**
- 日期:2026-08-12
- 决策者:用户(2026-08-12 技术方案 review 确认)
- 适用:[001-architecture §2.1](../design/001-architecture.md) `agentplatform/core/agent`

## 背景

平台核心是 agent 运行时,第一特色是"可复用 skill/tool + 显式调用"(模型 C)与消息渲染(21 种 renderer)。核心层面临选型:**自研 agent loop,还是引入现成 LLM agent 框架**(LangChain / LangGraph / CrewAI / OpenAI Agents SDK 等)。

001-architecture 此前一直假设自研,但未显式记录该决策及其理由。

## 决策

**自研核心 agent loop,不引入重量级框架;借鉴成熟设计模式。**

### 自研范围

- agent 调度循环(LLM 推理 → 显式调用 skill/tool → 结果回填 → 再推理)
- 会话状态机(空闲 / 推理中 / 等待工具 / 等待用户交互)
- LLM 网关(OpenAI 兼容客户端,流式转发、重试、端点配置)
- 显式调用编排(skill/tool 统一映射为 function-calling `tools`)
- 消息信封转换(`output_block` 拦截层,见 003 v2.0 §3.3)

### 借鉴的成熟模式(不引入框架,只采用其模式)

| 模式 | 借鉴来源 | 落地 |
|------|----------|------|
| ReAct / tool-use loop | ReAct、OpenAI Agents 实践 | 调度循环结构(001 §4.1) |
| 会话状态机 | LangGraph 状态图思想 | 手写状态枚举 + 转换表(见"影响") |
| 指数退避重试 | OpenAI SDK / 通用 | LLM 网关层重试,默认 3 次 |
| 流式转发 + SSE | SSE 协议 | API 层事件流(delta / block_meta / ...) |
| tool 循环上限 | 通用 agent 实践 | 每轮 max_tool_calls = 10,超限终止本轮 |
| checkpointing | LangGraph checkpoint 思想 | Redis 缓存活跃会话上下文(004 §4) |
| 上下文窗口管理 | 通用实践 | 历史超出预算时截断 + 摘要 |

### 不引入框架的边界

- 核心 loop 与调用协议**不依赖**任何第三方 agent 框架
- MVP 不引入 LangChain 系依赖;后续若某框架模块化到"可单点替换"且显著降复杂度,再评估
- 平台保持"自研 + 可插拔":未来可在调用协议层把外部 agent 以 skill 形式接入

## 理由

1. **第一特色要求完全掌控**:skill/tool 是平台级资源,显式调用语义 + 消息信封 + renderer 回传均为自定义,强框架绑定会限制调用协议
2. **无黑盒**:框架的调度 / 重试 / 上下文管理默认行为未必符合"显式调用 + 资源池"模型
3. **无升级绑架**:不引入框架则不受其 breaking change 影响
4. **核心 loop 本身不复杂**:复杂度在 skill/tool 语义与消息信封,而非调度;自研可控

## 影响

- `agentplatform/core/agent` 自研实现
- 会话状态枚举:`idle` / `thinking` / `awaiting_tool` / `awaiting_user` / `terminated`
- LLM 网关重试默认 3 次,指数退避
- 每轮 tool 调用上限 10 次
- 上下文管理:超出预算截断 + 摘要(具体策略实现阶段细化)
- MVP 依赖清单更轻(无 LangChain 系)

## 替代方案

### A. 引入 LangChain / LangGraph
- ✅ 调度 / 状态机 / checkpoint 现成
- ❌ 第一特色受框架语义约束;黑盒;升级绑架

### B. 引入轻量编排层(如只做 prompt 层的 smolagents / dspy)
- ✅ 部分借鉴
- ❌ 核心语义仍需自研,收益有限;MVP 不引入

### C(采用). 自研 + 借鉴模式
- ✅ 完全掌控;无黑盒;无升级绑架;依赖轻
- ❌ 开发量较大(MVP 范围内可控,核心 loop 约百行级)

## 相关决策

- [0001-namespace](./0001-namespace.md)
- 002-skill-tool-model 显式调用(模型 C)
- 003-message-rendering 消息信封 / `output_block` 拦截层
