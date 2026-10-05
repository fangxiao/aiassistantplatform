# 技术设计 · 任务实体化(022 · 对应需求 017)

- 文档版本:v0.1(20261006,与需求 017 同轮,方向确认中)
- 关联:019(M25 聚合层,保留)、011(定时任务,实体化对接)

## 1. 核心决策:轻实体,会话仍是执行载体

task 是**组织对象**不是执行对象:执行仍走会话(session_id 唯一引用,一对一);
定时任务经 scheduled_task 间接绑定。不重构 session/chat 链路,风险隔离在新增面。

## 2. 数据模型(迁移 tasks 表)

| 字段 | 说明 |
|---|---|
| id, user_id(index) | 归属 |
| title | 用户命名(默认取会话标题/任务名) |
| status | active / done / archived |
| kind | manual(会话提升)/ scheduled(定时任务) |
| session_id | 唯一(UQ),manual 的执行载体 |
| scheduled_task_id | kind=scheduled 时引用(定时任务删除→实体转 done) |
| created_at / completed_at | |

存量回填(一次性数据迁移):全部 scheduled_tasks → kind=scheduled 实体;
手动会话不回填(主动提升)。

## 3. API(prefix /tasks)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/tasks/from-session/{sid}` | 会话提升(409 若已提升) |
| GET | `/tasks?status=active\|done\|archived` | 实体列表(附 session/artifacts 计数) |
| PATCH | `/tasks/{id}` | 改名/状态流转(active↔done↔archived) |
| DELETE | `/tasks/{id}` | 仅删实体(会话与交付物保留) |

scheduler:创建定时任务时同步建实体;任务删除时实体置 done。

## 4. 聚合端点升级

`/workbench/tasks` 响应增 `tasks: [...]`(实体列表在前);原三栏保留为
「未提升会话」视图。前端任务中心改双区:我的任务(实体)/ 最近活动(聚合)。

## 5. 前端

- 会话页头部「⭐ 保存为任务」→ 命名弹窗 → 建实体
- 任务中心:实体列表(状态徽标/交付物计数/打开会话/完成/归档操作)
- 任务详情可先不做独立页:列表行展开 = 交付物行(复用 M25 artifact 行组件)

## 6. 测试要点

- 提升:唯一性 409/标题默认/artifacts 归集(按 session_id 关联查询)
- 流转:done 记时戳;archived 不出现在默认列表;DELETE 不级联会话
- scheduler 联动:建任务→实体存在;删任务→实体 done(单测 + 存量回填脚本测试)
- 聚合端点双区结构;web vitest 任务中心双区渲染
- E2E:提升会话→建产物→任务行计数→完成→归档

## 7. 落地记录(2026-10-06)

- 迁移 `b7d5f0a3c8e2`(表名 task_entities,避开与会话表概念混淆)+ 存量定时任务回填
- 实现与 §2-§5 一致;顺手修聚合端点变量遮蔽 bug(新增 tasks 列表被定时任务同名
  查询变量覆盖,测试捕获)
- E2E(live):提升会话→manual 实体(交付物归集 1)→重复提升 409→面板实体区双 kind
  并列(手动+定时)→PATCH done→active 面板移除、done 列表可见
- 全量 444 绿(新增 6);web vitest 11 绿(实体区双断言)
