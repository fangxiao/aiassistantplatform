# 任务拆解 · 个人工作台(M14)

- 文档版本:v0.1
- 日期:2026-09-14
- 依据:[010-workbench](../design/010-workbench.md)、[需求 007](../requirements/007-workbench.md)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T14.1 ✅ | 双视图容器:page.tsx 视图状态 + localStorage 记忆 + 常驻挂载切换(hidden) | - | P0 |
| T14.2 ✅ | WorkbenchView:问候头/快捷操作/我的助手/最近会话/知识库动态,独立降级 | T14.1 | P0 |
| T14.3 ✅ | 视图联动:onNewSession/onContinue/onOpenKb 回调接入既有 handler | T14.2 | P0 |
| T14.4 ✅ | **待办清单**(P1):localStorage 本地存储(`workbench_todos`),增删/勾选/清空已完成/看已完成;仅存本机不做同步,跨设备需求出现时迁云端表 | T14.2 | P1 |
| T14.5 ✅ | **每日简报**(P1):按钮触发,前端聚合 kb 规模+连接器状态注入 prompt,新建会话走 sendMessage 流式生成,展示后可「存入知识库」(复用收藏链路,source.app=workbench)或「继续追问」跳对话视图 | T14.2 | P1 |
| T14.6 | 主动服务/定时唤醒 agent(平台级能力,单独立项) | - | P2 |
| T14.7 ✅ | **待办 AI 联动 + 云端化**(P1.5):workbench_todos 表(迁移 e1c7f4b93a62);CRUD API(/api/workbench/todos,用户隔离,localStorage 一次性迁移导入);内置 `tool:workbench_todo`(add/list/toggle/delete,loop 按 kb_search 同款特判分发,user 上下文,所有会话默认注入);前端 TodoCard 切 API,AI 写入带 AI 徽标。端到端实测:对话"帮我记一条待办…"→ 助手调工具落库 | T14.4 | P1 |
| T14.8 ✅ | **P1.6 收尾六项**(设计 010 §3.2):数据源编辑弹窗;KB 动态失败重试;简报归档(近 7 份);通知铃铛(Navbar 全局,同步失败/待办汇总);空状态三步引导;助手卡管理入口 | T14.5, T14.7 | P1 |

验收对照需求 007 §4:高频路径 ≤1 跳转、卡片独立降级、切换不打断流式、P0 零后端 diff。
