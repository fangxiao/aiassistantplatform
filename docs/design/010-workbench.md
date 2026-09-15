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

## 3. P1 实现(2026-09-14)

- **待办卡**(TodoCard):localStorage `workbench_todos`,纯本地,UI 资产与业务资产分离的
  首个落地——本地不作为业务权威,迁云端表零包袱(需求 §数据分域原则)。
- **简报卡**(BriefingCard):按钮触发;前端聚合 kb 规模/连接器状态/**未完成待办**
  (T14.5 联动,TodoCard 云端化后同源可读)注入 prompt → createSession + sendMessage
  流式生成;产出可「存入知识库」(source.app=workbench)或「继续追问」(跳对话视图,
  简报会话保留可续)。非定时推送,主动唤醒留 P2。

## 3.1 待办云端化与 AI 联动(P1.5 · 2026-09-14)

AI 要写待办 → 待办从 localStorage 升级为**云端权威**(多方写入需一致存储,分域原则的
触发条件成立):`workbench_todos` 表按 user_id 隔离,origin 区分 manual/ai。

- **工具**:`tool:workbench_todo`(builtin,action=add/list/toggle/delete);loop 按
  kb_search 同款特判分发(db+owner_id 直传);chat 组装 resource 时**无条件注入**——
  平台级个人能力,对话里"帮我记一下…"即可生效,不要求助手声明依赖。
- **API**:`/api/workbench/todos` CRUD + `/completed` 清空 + `/import`(localStorage
  一次性迁移);前端 TodoCard 切 API,AI 写入带 AI 徽标,乐观更新。
- 旧 localStorage 数据首次加载自动上传云端后清本地(标记已迁移)。

## 3.2 P1.6 收尾六项(2026-09-15)

1. **数据源编辑弹窗**:DataSourcesPanel 复用创建表单,PATCH name/config/poll_interval——补齐"改频率要走 API"的管理缺口;
2. **KB 动态行动闭环**:失败/部分失败的源在动态卡直接「重试」(syncSource + 轮询);
3. **简报归档**:生成完成自动存档(本地 localStorage,保留近 7 份),卡片可展开回看;简报是生成物快照,本地合理,量大再上云;
4. **通知铃铛**(Navbar 全局):站内汇总式通知——同步失败源、未完成待办;未读以 localStorage 时间戳判定;服务端事件源(P2)接入时 UI 现成;
5. **空状态引导**:无助手且会话稀少时显示三步上手卡(选助手→传文档→让助手干活);
6. **助手卡管理入口**:hover 出现「管理 →」跳开发者中心。

## 4. 不做的事(P0/P1 红线)

- 零后端改动;零新表;待办/简报留 P1(本地存储/按钮触发);
- 对话视图内部逻辑一律不动。

## 4. 任务

见 [tasks/005-workbench.md](../tasks/005-workbench.md)。
