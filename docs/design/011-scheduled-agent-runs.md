# 011 · 定时唤醒 agent 设计(M15 · Scheduled Agent Runs)

- 文档版本:v0.1
- 日期:2026-09-15
- 流程阶段:阶段 2 · 设计
- 对应需求:[008-proactive-agents](../requirements/008-proactive-agents.md)
- 关联:010-workbench(产出落工作台)、009-content-connectors(调度器模式同源)、008-knowledge-base(运行时权限防御)

## 1. 架构总览

```
core/scheduler/scheduler.py(60s tick,复用连接器调度模式)
    │ 扫 scheduled_tasks: enabled 且 next_run_at ≤ now 且无 running run
    ▼
service.trigger_run ── asyncio 后台任务(独立 Session)
    │
    ├─ 自动创建会话(chat) + save_user_message(任务 prompt)
    ├─ 服务端聚合上下文(kind 模板:briefing = kb 动态 + 待办)
    ├─ run_agent(非流式聚合版;资源 = 助手依赖 ∪ todo ∪ kb_search)
    ├─ auto_save_kb → add_document_from_text(origin app=scheduler)
    ▼
task_runs(output/session_id/status) + task.next_run_at 顺延
    ▼
工作台:简报卡「自动生成」区 / 定时任务管理卡 / 通知铃铛(失败)
```

**复用而非新建**:会话链路(chat)、agent 循环(run_agent)、权限防御(M12)、
调度模式(连接器)、通知 UI(P1.6 铃铛)。平台唯一新概念是"任务与运行记录"两张表。

## 2. 数据模型(迁移 f9b3c7e25a01)

**scheduled_tasks**(定时任务)

| 字段 | 说明 |
|---|---|
| id, user_id, name, created_at/updated_at | |
| kind | briefing(晨报)/ inspection(巡检)/ custom(自定义)——kind 决定服务端聚合模板 |
| prompt | 任务指令(custom 必填;briefing/inspection 用内置模板,可附加补充要求) |
| schedule_type + daily_at / interval_minutes | daily("HH:MM")或 interval(分钟);cron 表达式留后续 |
| plugin_id nullable | 用哪个助手跑;空 = 平台通用助手 |
| mounted_kb_ids jsonb | 空 = 运行时取用户全部可见库(briefing 聚合同源);非空 = 声明范围(创建时校验可读) |
| auto_save_kb bool | 产出自动存知识库(存入用户默认可见的第一个可写库?——P0 存"共享工作区或首个可写库",后续做目标库选择) |
| enabled / last_run_at / next_run_at / last_status / last_error | 调度状态(next_run_at 持久化,重启恢复) |
| 配额 | settings.scheduler_max_tasks_per_user(默认 10),创建时校验 |

**task_runs**(运行记录,task 删除保留——审计,FK 无 cascade,task_runs.task_id 无 FK 约束)

| 字段 | 说明 |
|---|---|
| id, task_id, started_at, finished_at | |
| status | running / success / failed |
| output | 产出全文(工作台展示/存库来源) |
| session_id | 追溯会话(可"继续追问") |
| error | 失败摘要 |

## 3. 调度语义(设计 009 §6 同款 + 补充)

- tick(60s):`enabled AND (next_run_at IS NULL OR next_run_at ≤ now)` 且该任务无 running run
  → 触发;**错过不补跑**:执行后 next_run_at = 自 now 起的下个周期;
- next_run_at 计算:daily_at → 下一个该时刻(本地时区按服务器时区,MVP 简化);
  interval → now + interval;
- 首次创建 next_run_at = 立即算出(不立即执行;手动验证用「跑一次」);
- 运行超时上限:settings.scheduler_run_timeout_s(默认 600s),超时判失败;
- **无交互回填**:run_agent 遇 await_external 端侧工具降级路径本来就返回暂停文本,
  定时运行将其视为产出结束(文本含"等待外部"提示)——不失败不挂起,产出标注;
- 并发:同任务串行(running 拒绝);不同任务并行(asyncio task);
  全局并发上限 settings.scheduler_max_concurrent(默认 3),超出顺延到下个 tick。

## 4. 服务端聚合模板(kind)

| kind | 注入上下文 | 典型产出 |
|---|---|---|
| briefing | kb 动态(可见库 + 数据源最近状态)+ 未完成待办(前 5) | 每日简报 |
| inspection | 同 briefing,但 prompt 引导"仅报告异常与建议" | 巡检报告 |
| custom | 无注入,prompt 原样 | 自由 |

实现:`core/scheduler/context.py` build_context(db, user, kind) → dict。
**与前端 M14 聚合同源同义**(kb 列表/数据源/待办 API),前端简报保留(手动即时),
定时简报与之并列为"自动生成"。

## 5. API(prefix /scheduler)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/scheduler/tasks` | 列表(含 next_run_at/last_status)/新建(配额校验) |
| PATCH/DELETE | `/api/scheduler/tasks/{id}` | 改配置(重算 next_run_at)/删除(保留 runs) |
| POST | `/api/scheduler/tasks/{id}/run` | 手动跑一次(同自动路径,202) |
| GET | `/api/scheduler/tasks/{id}/runs?limit=10` | 运行记录 |
| GET | `/api/scheduler/runs/latest` | 当前用户最近一次成功产出(工作台简报卡"自动生成"区) |

全部 get_current_user 鉴权 + user_id 隔离;错误统一信封。

## 6. 工作台 UI

- **「⏰ 定时任务」卡**(简报卡旁):任务列表(名称/频率/下次运行/状态点)、新建/编辑弹窗
  (模板下拉 晨报/巡检/自定义 + prompt 补充框 + 频率 每天 HH:MM 或间隔 N 分钟 + 
  自动存知识库开关)、启停、跑一次、运行记录展开(产出全文/错误);
- **简报卡增强**:顶部"自动生成"区显示 `GET /runs/latest` 的产出(带时间),与手动简报并存;
- **通知铃铛**:新增 failed run 条目源。

## 7. 安全与风险

| 风险 | 缓解 |
|---|---|
| 定时任务失控消耗 tokens | 每用户任务数上限 + 单次超时 + 运行记录可见;停用开关一键 |
| 越权检索 | 挂载范围创建时校验可读;运行时 M12 防御分支(public 失效自动剔除) |
| 失败静默 | failed → 通知铃铛红色 + 任务 last_error 可见 |
| 多 worker 重复触发 | running run 拒绝重入(DB 状态);分布式锁规模化注记(同连接器) |
| 时区 | MVP 服务器时区;多时区用户留后续(记录于任务文档) |

## 8. 分期

- **P0(本设计)**:模型/迁移 + 调度执行器 + API + 工作台任务卡 + 简报卡自动区 + 通知接入 + 测试;
- **P1**:通知分级(仅异常才通知)、存库目标选择、创建模板丰富;
- **P2**:插件声明 schedules(plugin.yaml)、cron 表达式、通道推送。
