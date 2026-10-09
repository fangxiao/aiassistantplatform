# 任务拆解 · M30 定时任务推送体验与任务中心即时刷新(用户反馈 20261009)

## 背景(两项用户反馈)

1. 「任务保存后没有看到新的任务」——后端实体落库正常,根因是任务中心 60s
   轮询无事件通知,保存后立刻看不刷新
2. 「飞书机器人推送/邮件推送体验提升,选择已有的飞书机器人」——M22 P2-3 的
   `feishu_chat_id` 能力在 API(TaskIn)与 UI 双断层,从未在产品面打通

## 交付(20261009)

| 项 | 内容 |
|---|---|
| 即时刷新 | `ap:tasks-changed` 事件:定时任务增删改/手动运行/会话提升后广播,任务中心监听即时刷新(60s 轮询兜底) |
| 飞书推送打通 | TaskIn/TaskOut/编辑路径透传 `feishu_chat_id`;表单推送区「从已有会话选择」下拉(channel_sessions 真实会话,带可读 label)+ 手填兜底 + 在岗机器人缺失警示 |
| 测试推送 | POST /scheduler/push-test(限频 1/10s/用户),表单「测试」按钮即时验证通道 |
| 目标发现 | GET /scheduler/push-targets:飞书会话列表 + 在岗机器人 + SMTP 配置状态 |
| 邮件提示 | SMTP 未配置时表单明示「发送不会生效」 |

## 验证

- pytest 3 用例(目标列表/限频/字段透传),全量 454 绿;web tsc 绿
- E2E(live):push-targets 返回真实会话;push-test 真实投递 studyassistant 群成功

## 事故记录(20261009 晚):僵尸 run

**现象**:用户任务「跑一次」后永久"正在运行中",无终态/无推送/无产出,任务行置灰。

**根因**:`trigger_run` 的 `asyncio.create_task` 未保存强引用——事件循环对 task 仅持
弱引用,**后台执行体可能被 GC 中途回收 → CancelledError**,而 `except Exception`
抓不住它(BaseException)→ 直接跳 finally 只记 finished_at,status 永远 running。
两条僵尸 run(3/9 分钟随机中断)与全部观察吻合:无日志、error 空、finished_at 有值。

**修复**:
1. 根治:`_BG_RUN_TASKS` 强引用集合(done_callback 弃引)
2. finally 自愈:走到终局仍 running → 判 failed 留痕(兜底一切逃逸路径)
3. 僵尸清道夫:tick 每轮先修历史坏数据(僵尸会永久占满并发额度)
4. 会话即绑:run 开始就写 session_id 并提交——运行中任务行可点开执行现场

**测试补强**:reaper 2 用例(僵尸判失败/健康 run 不动),全量 458 绿;
E2E 真实链复验(success + 飞书推送 + 交付物 + 行可点)。

**教训(对"测试用例缺失"怀疑的回应)**:此类 bug 属「真实时序 + 运行时生命周期」
类,单元测试结构性抓不住——需要:① 用户旅程级 E2E(Playwright,待办 C2);
② 长跑冒烟(定时任务真实连跑多轮)。已列入补强计划。
