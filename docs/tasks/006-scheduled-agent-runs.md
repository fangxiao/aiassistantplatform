# 任务拆解 · 定时唤醒 agent(M15)

- 文档版本:v0.1
- 日期:2026-09-15
- 依据:[011-scheduled-agent-runs](../design/011-scheduled-agent-runs.md)、[需求 008](../requirements/008-proactive-agents.md)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T15.1 ✅ | 数据模型与迁移:scheduled_tasks / task_runs(运行记录随任务删除保留)+ settings 配置 | - | P0 |
| T15.2 ✅ | 上下文聚合模板:core/scheduler/context.py(briefing/inspection = kb 动态 + 待办,与前端 M14 聚合同源) | T15.1 | P0 |
| T15.3 ✅ | 调度执行器:core/scheduler/{service,scheduler}.py——trigger_run(自动会话 + run_agent 非流式)、next_run_at 计算(错过顺延)、running 拒绝、并发上限、超时、配额;lifespan 启停 | T15.2 | P0 |
| T15.4 ✅ | API:/api/scheduler/tasks CRUD + /run + /runs + /runs/latest;user 隔离 | T15.3 | P0 |
| T15.5 ✅ | 工作台:「⏰ 定时任务」卡(列表/新建编辑弹窗/启停/跑一次/运行记录)+ 简报卡"自动生成"区 + 通知铃铛 failed 源 | T15.4 | P0 |
| T15.6 ✅ | 测试:next_run_at 计算、执行器(假 LLM 产出落 run、失败落 error、权限隔离)、API 鉴权/配额;全量回归 | T15.4 | P0 |
| T15.7 | 通知分级(仅异常通知)/存库目标选择/模板丰富 | T15.6 | P1 |
| T15.8 | 插件声明 schedules(plugin.yaml)/ cron 表达式 / 通道推送 | T15.6 | P2 |

验收对照需求 008 §4:P0 覆盖 1/2/3/4/5/6/7/8 全部八条(2=重启恢复由 next_run_at 持久化 + 启动即扫保证)。
