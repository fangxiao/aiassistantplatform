# 任务拆解 · 个人工作台(M14)

- 文档版本:v0.1
- 日期:2026-09-14
- 依据:[010-workbench](../design/010-workbench.md)、[需求 007](../requirements/007-workbench.md)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T14.1 ✅ | 双视图容器:page.tsx 视图状态 + localStorage 记忆 + 常驻挂载切换(hidden) | - | P0 |
| T14.2 ✅ | WorkbenchView:问候头/快捷操作/我的助手/最近会话/知识库动态,独立降级 | T14.1 | P0 |
| T14.3 ✅ | 视图联动:onNewSession/onContinue/onOpenKb 回调接入既有 handler | T14.2 | P0 |
| T14.4 | 待办清单(P1,localStorage 本地存储 + output_block 交互添加约定) | T14.2 | P1 |
| T14.5 | 每日简报(P1,按钮触发生成,复用会话链路与收藏) | T14.2 | P1 |
| T14.6 | 主动服务/定时唤醒 agent(平台级能力,单独立项) | - | P2 |

验收对照需求 007 §4:高频路径 ≤1 跳转、卡片独立降级、切换不打断流式、P0 零后端 diff。
