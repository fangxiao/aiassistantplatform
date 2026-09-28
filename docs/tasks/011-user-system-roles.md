# 011 · 用户体系与角色权限(M20)

基于设计 015 与 ADR 0008 拆解,标注依赖与优先级。

| 编号 | 任务 | 依赖 | 优先级 | 状态 |
|---|---|---|---|---|
| T20.1 | 角色层级制基础:`UserRole` 增 `admin`(PG enum `ALTER TYPE ADD VALUE` 迁移);`users.disabled_at` 字段;`core/auth/dependencies.py` 新增 `is_admin`/`is_developer`/`require_admin`/`require_developer` 层级辅助函数;登录与 token 校验拒绝 disabled 账号 | — | P0 | ✅ 2026-09-28 |
| T20.2 | bootstrap:`INITIAL_ADMIN_EMAIL`(+可选 `INITIAL_ADMIN_PASSWORD`)启动时幂等升级/创建首个 admin;未配置跳过;`allow_self_promote_developer` 保留仅本地开发 | T20.1 | P0 | ✅ 2026-09-28 |
| T20.3 | 现状门槛迁移(设计 015 §4.2 七处):`admin_llm.py`、`insights.py`(全局)、`notify.py`(platform 渠道)→ `require_admin`;`plugins.py` 挂载知识库、`assistant_access.py` 插件侧 → `require_developer`;清理全部直接 `role != UserRole.developer` 比较;regression:原 developer 用户平台管理接口 403、插件开发接口 200 | T20.1 | P0 | ✅ 2026-09-28 |
| T20.4 | 发布审批数据模型:`plugins` 增 `review_status`(pending_review/approved/rejected,默认 pending_review)/`last_review_reason`/`reviewed_by`/`reviewed_at`;存量 active 插件一次性置 approved;deploy 收紧为必须登录+developer,owner_id 必填 | T20.1 | P0 | ✅ 2026-09-28 |
| T20.5 | 审批流 API:`POST /plugins/{id}/review`(approve/reject+reason,admin)、`POST /plugins/{id}/resubmit`(owner,清 reason 回 pending);`list_plugins` 可见性过滤收敛一处(owner/admin 全量,其余 active+approved);enable/disable 收敛 admin(owner 对自己插件的 disable 豁免);uninstall/调 himself 限 owner+admin | T20.4 | P0 | ✅ 2026-09-28 |
| T20.6 | `/a/{token}` 白牌入口审批约束:未过审助手仅 owner/admin 可进入,其余 404;前端助手广场/列表同步过滤未过审项(owner 可见带"待审核"标记) | T20.5 | P0 | ✅ 2026-09-28 |
| T20.7 | 用户管理 API(admin):列表/搜索、改角色、禁用/启用;不做注册审批 | T20.1 | P1 | ✅ 2026-09-28 |
| T20.8 | insights 拆两档:admin 全局(现状),developer 新增"仅自己插件"用量洞察(owner_id 过滤) | T20.3 | P1 | ✅ 2026-09-28 |
| T20.9 | web 前端:admin 审批操作入口(助手管理页 approve/reject + 原因)、用户管理页(角色/禁用)、角色徽标展示;导航栏角色校准沿用 7336fe1 机制 | T20.5,T20.7 | P1 | ✅ 2026-09-28 |
| T20.10 | 测试收口(设计 015 §8 五要点):层级制/迁移回归/审批闭环/bootstrap 幂等/token 入口约束;pytest 覆盖 + `agentplatform test` 不受影响确认 | T20.1-T20.8 | P0 | ✅ 2026-09-28 |

## 依赖关系

```
T20.1 ──┬── T20.2 ──┐
        ├── T20.3 ──┼── T20.8
        └── T20.4 ── T20.5 ── T20.6
T20.1 ── T20.7
T20.5 + T20.7 ── T20.9(前端)
全部 ── T20.10
```

P0 = 后端闭环(T20.1-T20.6, T20.10),P1 = 管理面与前端(T20.7-T20.9)。

## 落地记录(2026-09-28)

- 全部 10 项完成;pytest 362 绿(新增 test_user_roles_api 12 项),web tsc/vitest 绿
- 迁移前置:发现 T18.20(c9d5e3b72f81)热更未走 alembic 的漂移 → stamp + merge(85b6a2fdaa2d)+ 本次 b3e9c4a6d715
- CLI deploy 同步收紧:未配置令牌显式报错(401/403 分支提示)
- insights 门槛收敛:admin/users、admin/overview、/actions → require_admin;/insights/costs 按 owner 过滤支持 developer 自有口径
- E2E 冒烟(live):注册→403 门槛→psql 提权→部署 pending→未过审不可见→/a/{token} 404→reject 422/驳回→重提→approve 全员可见→join 200→禁用登录 401/旧 token 403,全部符合预期
