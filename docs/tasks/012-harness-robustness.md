# 任务拆解 · Agent Harness 加固(012 · 对应需求 011 / 设计 016)

- 日期:2026-09-29
- 流程阶段:阶段 3 · 任务拆解
- 分期:P1 → P2 → P3,每期独立交付、独立开关、可回退

## P1 · 断线检查点与续跑(H1,当前期)

| # | 任务 | 依赖 | 产出 |
|---|---|---|---|
| P1.1 | alembic:`messages.is_draft` | - | migration |
| P1.2 | message 模型/服务:is_draft 字段 + `latest_draft_message` + `finalize_draft_message` | P1.1 | core/message |
| P1.3 | api/chat.py:草稿检查点流——流开始建草稿,tool_call 边界/字符阈值 flush,done finalize,异常路径保存 partial(不再整轮丢弃),error 事件携带 `resumable` | P1.2 | 主消息端点改造 |
| P1.4 | chat/service.py:`history_override` 参数(续跑用历史) | - | core/chat |
| P1.5 | resume 端点 `POST /sessions/{sid}/resume`:定位草稿 → 以含草稿的历史 + 内部续跑指令重启 agent → 结果并入草稿 finalize | P1.2-P1.4 | 新端点 |
| P1.6 | web:error 消息上的「从断点续跑」按钮,按 `resume_of` 原位替换渲染 | P1.5 | web/app/page.tsx |
| P1.7 | 测试:草稿留存/异常 partial/resume 定位与 finalize;断流注入用例 | P1.3-P1.5 | pytest |
| P1.8 | 部署 + 线上冒烟(人为中断 → 续跑) | P1.7 | 验证记录 |

验收对齐需求 011:A1(断线自动续跑)、A2(结构化错误 + 断点重试)。

## P2 · 错误分类 + 并发重构(H4 + H2)

| # | 任务 | 产出 |
|---|---|---|
| P2.1 | errors.py 六类枚举 + 策略绑定(ADR 0010) | core/agent/errors |
| P2.2 | alembic:`agent_round_trace` 表 + 写入点(轮次/压缩/兜底计数) | migration |
| P2.3 | SSE error 统一 `{code,kind,message,resumable}` | api 层 |
| P2.4 | loop.py 拆分:dispatch.py(工具调用解析/资源匹配迁出)、loop 瘦身 ≤400 行 | 设计 016 §3 |
| P2.5 | 轮询消除:skill_delta_queue/progress_q → 生成器合并,子调用失败结构化上报 | 设计 016 §3.2 |
| P2.6 | 故障注入矩阵测试(子调用失败/session 失效/解析失败) | 验收 A4 |

## P3 · 上下文压缩 + 兜底收缩(H3 + H5)

| # | 任务 | 产出 |
|---|---|---|
| P3.1 | alembic:MessageRole.summary + llm_endpoints.supports_native_tools | migration |
| P3.2 | context.py:token 计量、阈值触发、滚动摘要、频率闸 | 设计 016 §4 |
| P3.3 | 摘要可知情:工作台"查看上下文摘要"入口 + 渲染层跳过 summary | web |
| P3.4 | dispatch 按 supports_native_tools 分流 + text_fallback 计数落 trace | 设计 016 §6 |
| P3.5 | 50 轮会话 token 上界用例 + 摘要保留约束用例 | 验收 A3/A6 |
