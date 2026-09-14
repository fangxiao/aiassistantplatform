# 010 · 个人工作台设计(M14 · 路线 A)

- 文档版本:v0.1
- 日期:2026-09-14
- 流程阶段:阶段 2 · 设计
- 对应需求:[007-workbench](../requirements/007-workbench.md)

## 1. 双视图架构

首页 `/` 变为双视图容器,两视图**常驻挂载**(CSS 隐藏切换,不卸载)——
对话视图的流式响应、消息状态在切去工作台后继续,切回无损:

```
page.tsx(ChatHome)
├── Navbar
├── [view=workbench] WorkbenchView      ← 新增 dashboard(独立组件,降级容错)
└── [view=chat]      对话区(SessionDrawer + 聊天,现有不动)
```

- 视图状态 `view: "workbench" | "chat"`,localStorage `workbench_view` 记忆;
  首次访问默认工作台。
- 切换组件用 `className="hidden"` 而非条件渲染(保持挂载是硬要求)。
- 联动回调:工作台 `onNewSession(assistantId?)` / `onContinue(sessionId)` / `onOpenKb()`
  → page.tsx 既有 handler + 切到 chat 视图。

## 2. WorkbenchView 组件(web/components/workbench/)

| 区块 | 数据源 | 降级 |
|---|---|---|
| 问候头 | 本地时间 | - |
| 快捷操作 | 无(3 个入口:新会话→助手弹窗逻辑复用/问知识库→/kb、上传文档→/kb) | - |
| 我的助手 | GET /api/assistants(前 6 个;卡上显示挂载库数 mounted_kb_ids?.length) | 占位卡 |
| 最近会话 | GET /api/chat/sessions(前 8,点击 → onContinue) | 占位行 |
| 知识库动态 | GET /api/kb/kbs + 每库 GET sources(N≤10;显示最近同步状态/处理中文档) | 占位卡 |

- 每卡片独立 loading/error,互不阻塞(需求 NFR);
- 知识库动态轮询复用 2.5s 仅当存在 running 同步或中间态文档。

## 3. 不做的事(P0 红线)

- 零后端改动;零新表;待办/简报留 P1(本地存储/按钮触发);
- 对话视图内部逻辑一律不动。

## 4. 任务

见 [tasks/005-workbench.md](../tasks/005-workbench.md)。
