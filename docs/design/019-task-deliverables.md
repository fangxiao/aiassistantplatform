# 技术设计 · 任务面板与交付物(019 · 对应需求 014)

- 文档版本:v0.1(20261006,与需求 014 同轮)
- 流程阶段:阶段 2 · 设计
- 关联:011-scheduled-agent-runs(task_runs 复用)、010-workbench(面板挂载点)、
  018-auth(权限口径沿用 get_current_user)

## 1. 核心决策:聚合层,不做任务实体

「任务」在本期 = **聚合视图**,不是新表:进行中 = 活跃会话 ∪ running 的 task_runs;
交付物 = 新增 artifacts 登记表。不动会话/调度模型,验证用户价值后再谈实体化。

## 2. 数据模型(迁移 `artifacts`)

**artifacts**(交付物登记)

| 字段 | 说明 |
|---|---|
| id, user_id(index) | 归属 |
| session_id nullable / task_run_id nullable | 产生来源(跳转用,二选一或皆空) |
| kind | `html` / `image` / `report`(定时任务产出) |
| title | 展示名(args 提示词截断 40 字 / 任务名+日期) |
| path | 相对路径(uploads 下);**展示时现签 URL**(签名有 TTL,落库即过期) |
| meta jsonb | 预留(资源名、模型等) |
| created_at | 倒序取最近 |

不存签名后的完整 URL;report 类 path 为空,凭 task_run_id 跳会话。

## 3. 登记埋点

### 3.1 工具产出(loop 层)

`execute_tool` 无会话上下文 → 登记点放在 **loop.stream_agent 的工具结果回流处**:

- `stream_agent`/`run_agent` 新增可选参数 `chat_session_id`(调用方:api/chat.py、
  scheduler/service.py、channel/feishu.py 各传一行;不传则不登记,兼容既有测试)
- 资源名白名单 `tool:html_render` / `tool:image_gen` 命中后,从结果字符串提取
  `/api/files/...` 相对路径(正则),登记 artifacts(user=owner_id, title=args
  提示词截断)
- 登记 try/except 包裹,失败仅日志——闭环自愈(需求 A2)

### 3.2 定时任务产出(scheduler 层)

`trigger_run` 成功落 task_runs 后登记一条 kind=report(title=`{task.name} · {MM-DD}`,
task_run_id + session_id 双引用)。失败不登记(面板的定时栏已可见 last_status)。

## 4. 聚合端点

`GET /api/workbench/tasks`(prefix 沿用 workbench 路由,get_current_user 鉴权):

```
{
  running:   [活跃会话(近 30min 有消息,取 5)+ running task_runs(取 5)]
             — 会话含插件名/最后消息摘要/updatedAt;run 含任务名/startedAt
  scheduled: [enabled 任务,按 next_run_at 排序取 8:名称/next_run_at/last_status]
  artifacts: [最近 30 条:id/kind/title/created_at/session_id(可跳)/signed_url(现签)]
}
```

- 三路各一条查询,DB 压力可忽略(均 user_id 过滤 + 索引)
- 白牌 `/a/{token}` 走 assistant_access,不挂 workbench 路由 → 天然不暴露

## 5. 前端(工作台)

- `TasksCard`(新组件,置于 TodoCard 之上):三段式
  - 进行中:条目点击 → onContinue(session)复用工作台跳转;run 条目 → 定时任务卡
  - 定时任务:摘要行(下次运行/状态徽标),「管理」跳 SchedulerCard
  - 交付物:图标(kind)+ 标题 + 时间;点击新窗口打开 signed_url;
    「继续」跳会话;「存 KB」复用 SaveToKbModal 文本入口(report 类传 run output)
- 拉取时机:进入工作台一次 + 每 60s 轮询(与 BriefingCard 同节奏,不引 SSE)

## 6. 测试要点

- 埋点:html_render/image_gen 产出登记(传/不传 chat_session_id 两态)、登记异常不炸工具
- 聚合端点:三栏结构、user 隔离、report 双引用跳转字段
- scheduler:成功登记、失败不登记
- web:TasksCard vitest(空态/三栏渲染/跳转回调)
- E2E 冒烟:发起图片生成 → 面板交付物出现 → 点击可开 → 跳会话可继续

## 7. 落地记录(2026-10-06)

- 迁移 `e4a7c9f2d5b1`;全量 pytest 411 绿(新增 8),web vitest 11 绿(新增 4),tsc 绿
- 实现与 §2-§5 一致,补充两点:
  1. 埋点复用 loop 既有的 `execute()` 包装层与 URL 提取正则(M17 交付链同源);
     `chat_session_id` 由 chat service / scheduler 传入,feishu 通道经 chat service 自动覆盖
  2. 聚合端点为 report 类附加 `content`(run output 截 4000 字)支撑「存 KB」;
     文件类 `signed_url` 现签(public_api_base 拼绝对地址)
- E2E 冒烟(live):①run_agent 真实调 image_gen → artifacts 落行(kind/title/path/session
  全对),面板显示现签 URL;②定时任务真实跑一次(真实 LLM)→ report 登记(title 带
  任务名+日期、session_id 关联、content 摘要),scheduled 栏状态 success;③进行中栏
  聚合活跃会话与自动创建的任务会话;④user 隔离(他人数据不可见)单测覆盖
- 已知取舍:定时任务自动创建的会话标题为「未命名会话」(沿用既有行为,未在本期美化)
