# 任务拆解 · M25 任务面板与交付物(对应需求 014 / 设计 019)

- 日期:2026-10-06
- 流程阶段:阶段 3 · 任务拆解(当日实现收口)
- 规模预估:后端 ~1.5 天 + 前端 ~1 天 + 测试冒烟 ~0.5 天

| # | 任务 | 依赖 | 产出 | 优先级 | 状态 |
|---|---|---|---|---|---|
| T25.1 | alembic 迁移:artifacts 表(user_id 索引/created_at 倒序) | — | migration `e4a7c9f2d5b1` | P0 | ✅ 20261006 |
| T25.2 | artifacts 模型 + 登记服务(core/artifacts,失败静默日志) | T25.1 | core | P0 | ✅ 20261006 |
| T25.3 | loop 埋点:stream_agent/run_agent 增 `chat_session_id` 可选参;execute 包装层按白名单登记;chat/scheduler 调用方传参(feishu 走 chat service 自动覆盖) | T25.2 | core/agent | P0 | ✅ 20261006 |
| T25.4 | scheduler 登记:trigger_run 成功后 kind=report 条目(双引用) | T25.2 | core/scheduler | P0 | ✅ 20261006 |
| T25.5 | 聚合端点 `GET /api/workbench/tasks`(三栏,user 隔离,现签 URL,report 带内容摘要) | T25.1 | api/workbench | P0 | ✅ 20261006 |
| T25.6 | web TasksCard:三段式渲染/跳会话/开产物/report 存 KB;工作台挂载 + 60s 轮询 | T25.5 | web/workbench | P1 | ✅ 20261006 |
| T25.7 | 测试:test_task_deliverables 8 用例 + TasksCard vitest 4 用例;全量 pytest 411 绿;web tsc+vitest 11 绿 | T25.3-T25.6 | tests | P0 | ✅ 20261006 |
| T25.8 | 部署 + 冒烟:真实 image_gen 全链(登记+面板)、真实定时任务(报告登记+内容)、聚合端点逐栏核对 | T25.7 | 验证记录(设计 019 §7) | P0 | ✅ 20261006 |
| T25.9 | 文档同步:需求/设计落地记录 | T25.8 | docs | P1 | ✅ 20261006 |

## 依赖关系

```
T25.1 ── T25.2 ──┬── T25.3 ──┐
                 ├── T25.4 ──┼── T25.5 ── T25.6 ── T25.7 ── T25.8 ── T25.9
                 └───────────┘(T25.4 与 T25.3 并行)
```

## 验收对齐需求 014:A1(面板三栏)、A2(登记自愈)、A3(打开/跳转/存KB)、A4(聚合端点+隔离)、A5(不回填/白牌不暴露)
