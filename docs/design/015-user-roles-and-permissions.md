# 015 · 用户体系与角色权限设计

- 文档版本:v0.1(草案)
- 日期:2026-09-28
- 流程阶段:阶段 2 · 设计
- 对应需求:平台用户体系(管理员/开发者/普通用户)
- 关键决策:ADR 0008

---

## 1. 目标与背景

平台与各助手**共享一套用户体系**:助手不自建用户,统一由平台注入身份(JWT),
数据按 `user_id` 隔离。

角色三档:

| 角色 | 定位 | 管什么 |
|------|------|--------|
| admin(平台管理员) | 平台运营层 | 用户与角色管理、平台级配置(LLM 端点、通知渠道)、发布审批、全局洞察、未来计费配置 |
| developer(开发者) | 插件开发生态 | 创建/调试/发布**自己的**助手、插件密钥、自己插件的用量洞察、开发者 CLI |
| user(普通用户) | 使用层 | 对话、会话历史、个人知识库、反馈、使用已过审的助手 |

**权限层级制**(ADR 0008):`admin ⊃ developer ⊃ user`。

## 2. 数据模型变更

### users(改)

| 字段 | 变更 | 说明 |
|------|------|------|
| role | enum 增 `admin` | `user / developer / admin`;PG enum 迁移需 `ALTER TYPE ... ADD VALUE` |
| disabled_at | timestamptz 可空,新增 | 禁用账号(登录拒绝、token 校验拒绝);初期可只建字段+校验逻辑,不做管理 UI |

### plugins(改)

| 字段 | 变更 | 说明 |
|------|------|------|
| review_status | enum,新增 | `pending_review / approved / rejected`;默认 `pending_review` |
| last_review_reason | text 可空,新增 | 驳回原因;重提/过审时清空 |
| reviewed_by / reviewed_at | fk/timestamptz 可空,新增 | 审计 |

现有 `status(active/disabled)` 语义不变(启停开关),与审批状态正交:
**全员可见 = `status=active` 且 `review_status=approved`**。

历史数据迁移:存量 `active` 插件一次性置为 `approved`(平台初期的既有助手由 admin 背书),
避免上线即全员不可用。

## 3. 鉴权辅助函数(`core/auth/dependencies.py` 扩展)

```python
def is_admin(user) -> bool
def is_developer(user) -> bool          # admin 亦为真(层级制)
async def require_admin(user = Depends(get_current_user))
async def require_developer(user = Depends(get_current_user))  # admin+developer
```

业务代码**不再直接比较 `role != UserRole.developer`**,统一替换为上述依赖;
鉴权失败返回 403 `{error:{code:"forbidden", ...}}`(005 §1 错误信封)。

## 4. 权限矩阵与现状迁移清单

### 4.1 目标权限矩阵

| 资源/操作 | user | developer | admin |
|-----------|:----:|:---------:|:-----:|
| 使用已过审助手、管理自己的会话/个人知识库 | ✅ | ✅ | ✅ |
| 部署/调试/卸载**自己的**插件 | ❌ | ✅ | ✅ |
| 挂载知识库、申请发布 | ❌ | ✅ | ✅ |
| 查看自己插件的用量洞察 | ❌ | ✅ | ✅ |
| 审批/驳回他人插件、启停任意插件 | ❌ | ❌ | ✅ |
| 用户管理(角色分配、禁用) | ❌ | ❌ | ✅ |
| LLM 端点管理(`admin_llm.py`) | ❌ | ❌ | ✅ |
| 平台通知渠道(`notify.py` platform) | ❌ | ❌ | ✅ |
| 全局洞察(`insights.py`) | ❌ | ❌ | ✅ |

### 4.2 现状迁移清单(现状 developer 门槛 → 目标角色)

| 位置 | 现状 | 目标 |
|------|------|------|
| `api/admin_llm.py:35,47` | `role != developer` 拒绝 | `require_admin` |
| `api/insights.py:23` | `role != developer` 拒绝 | `require_admin`;developer 侧新增"仅自己插件"的洞察查询(owner_id 过滤) |
| `api/notify.py:84,109` | platform 渠道卡 developer | `require_admin` |
| `api/plugins.py:111`(挂载知识库) | `role != developer` | `require_developer`(语义不变) |
| `api/plugins.py` deploy/enable/disable/uninstall | 仅要求登录 | deploy/uninstall 限 owner+admin;enable/disable 收敛为 admin(启停是运营动作) |
| `api/assistant_access.py:78,96` | developer 门槛 | 随上述语义对齐 |
| `core/auth/model.py:17` | enum 两档 | 增 `admin`;`allow_self_promote_developer` 保留仅本地开发 |

**"自己的插件"判定**:插件无 owner 列比较逻辑时以 `plugins.owner_id == str(user.id)`
为准(admin 豁免);deploy 时 `get_optional_current_user` 未登录返回 anonymous 的行为
随审批制收紧为必须登录 + developer 角色。

## 5. 发布审批流程

```
developer deploy ──► pending_review(仅 owner+admin 可见可试)
                        │
        owner 重新提交  ◄─── rejected(admin 驳回,附 last_review_reason)
                        │
                   admin approve ──► approved(全员可见,entry 广场/列表)
                        │
                   admin disable ──► 下架(保留 approved,reject 用 disable 表达)
```

- API:`POST /plugins/{id}/review`(approve/reject + reason,`require_admin`),
  `POST /plugins/{id}/resubmit`(owner,清空 reason、回 `pending_review`);
- 列表过滤收敛**一处**(`list_plugins` 的可见性条件):owner/admin 全量,
  其余用户仅 `active + approved`;未来付费分层只在此处加 `access_tier` 条件(§7);
- `/a/{token}` 白牌入口(T18.20):未过审助手仅 owner/admin 可进入,其余 404;
- 部署覆盖(ADR 0007 原地 upsert)保留 `review_status` 与 UUID:小版本重部署不退回
  审批由 admin 酌情;初期实现取**保守策略——重新部署一律回 `pending_review`**,
  owner 可催审,避免"过审后偷换内容"。

## 6. 用户管理与首个 admin

- 用户管理 API(`require_admin`):列表/搜索、改角色、禁用/启用;不做注册审批;
- 注册默认 `user`;`allow_self_promote_developer=True` 仅本地开发可自选 developer
  (现状保留);线上 developer/admin 一律由 admin 在用户管理中指派;
- **bootstrap**:`INITIAL_ADMIN_EMAIL`(+ 可选 `INITIAL_ADMIN_PASSWORD`),应用启动时:
  该邮箱存在 → 升为 admin;不存在 → 创建;幂等,重复启动无副作用;
  未配置则跳过(本地开发不受影响)。

## 7. 未来收费的预留口子(本期不实现)

1. 助手可见性判断收敛于 §5 的单处过滤函数 → 未来加 `access_tier(free/paid)`
   与用户订阅表只改一处;
2. `insights.py` 已有 tokens 聚合,是未来按量计量的底子;用户维度 quota 届时再加表;
3. 角色仍是三档层级,不因收费引入新角色(付费状态是**用户属性**,不是角色)。

## 8. 测试要点(阶段 5 对应)

- 层级制:admin 可执行全部 developer 操作;user 被 `require_developer` 拒绝;
- 迁移回归:原 developer 用户登录后,平台管理接口 403、插件开发接口 200;
- 审批流:deploy 后普通用户列表不可见 → approve 后可见 → reject + resubmit 闭环;
- bootstrap:重复启动幂等;未配置环境变量无副作用;
- `/a/{token}`:未过审仅 owner/admin 可入,其余 404。
