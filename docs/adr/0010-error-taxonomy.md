# ADR 0010 · 错误分类六类枚举 + 轮次追踪表

- 状态:已接受(2026-09-29)
- 关联:需求 011 H4 / 设计 016 §5

## 背景

运行时错误长期靠事故驱动逐个打补丁:20260926 表单三连崩、20260928 嵌套流
静默失败与 DetachedInstanceError、20260929 部署态断线静默降级。每类故障都要
用户先踩一遍;排查依赖读源码。根因是没有统一的错误分类与处理策略声明。

## 决策

1. `agent/errors.py` 定义六类错误枚举:`transient / checkpoint_resume /
   tool_failure / deploy_broken / contract / internal`,每类绑定处理策略
   (重试预算、用户话术、日志级别)与 `resumable` 标记;
2. 新表 `agent_round_trace` 逐轮记录:轮次、类型(chat/skill/tool/compaction)、
   工具调用路径(native/text_fallback)、token 用量、错误分类与详情;
3. SSE `error` 事件统一为 `{code, kind, message, resumable}`;
4. 新错误类型接入流程:先归入既有类并补策略声明,不允许裸抛裸吞。

## 备选与理由

- **引入外部可观测性栈(OTel/Sentry)**:能力过剩,新增基础设施违反需求 011
  非功能约束 1;trace 表 + 结构化日志已满足排查需要,后续需要时再桥接;
- **仅日志不落库**:日志无结构、难关联会话与轮次,压缩事件(H3)与兜底计数(H5)
  也需要落点,trace 表一表多用。

## 后果

- 每轮一次 INSERT,量级与会话数线性,可接受(PG 单表,按 created_at 清理);
- loop/executor 对错误构造点需显式归类,短期改造成本换长期可维护。
