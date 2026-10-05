# 任务拆解 · M26 注册表热度与一键引用(对应需求 015 / 设计 020)

- 日期:2026-10-06
- 流程阶段:阶段 3 · 任务拆解(当日实现收口)
- 规模预估:后端 ~0.5 天 + 前端/CLI ~0.5 天 + 测试 ~0.5 天

| # | 任务 | 依赖 | 产出 | 优先级 | 状态 |
|---|---|---|---|---|---|
| T26.1 | alembic 迁移:`skill_tools.use_count` | — | migration `f5b8d2e7c4a9` | P0 | ✅ 20261006 |
| T26.2 | loop 埋点:execute() 包装层 `bump_use_count`(id+version 快照,service 层静默自愈) | T26.1 | core/agent/loop + registry/service | P0 | ✅ 20261006 |
| T26.3 | manifest 注入:条目带 use_count(usage_by_id 跨版本 SUM,离线回退 0);specs 端点走 get_session 依赖(测试隔离) | T26.1 | core/registry/capabilities + api/specs | P0 | ✅ 20261006 |
| T26.4 | registry API:SkillToolOut 加 use_count、`sort=usage`(缺省行为不变) | T26.1 | api/registry | P1 | ✅ 20261006 |
| T26.5 | web registry tab:热度徽标(🔥N/NEW)+ 默认热度排序(复制引用按钮 P1 前已存在,复用) | T26.3 | web/developer | P1 | ✅ 20261006 |
| T26.6 | CLI registry:条目按热度排序 + `[🔥 N 次/NEW]` 标记 | T26.3 | cli/main | P2 | ✅ 20261006 |
| T26.7 | 测试:test_registry_usage 5 用例(自增/跨版本 SUM/离线回退/sort 兼容/端点携带);全量 416 绿;web tsc+vitest 绿 | T26.2-T26.5 | tests | P0 | ✅ 20261006 |
| T26.8 | 部署 + 冒烟:真实 run_agent 调 pdf_parse → 计数 0→1;sort=usage 榜单榜首变化;web 200 | T26.7 | 验证记录 | P0 | ✅ 20261006 |
| T26.9 | 文档同步:需求/设计落地记录 | T26.8 | docs | P1 | ✅ 20261006 |

## 验收对齐需求 015:A1(计数)、A2(透出/排序)、A3(复制引用)、A4(徽标)、A5(CLI 列)
