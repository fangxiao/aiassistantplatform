# ADR 0008 · 用户角色层级制、环境变量引导首个 admin、发布审批制

- 状态:已接受
- 日期:2026-09-28
- 背景:现有 `UserRole` 仅 user/developer 两档,`developer` 同时承担"插件开发者"与
  "平台管理员"两类职责(`admin_llm.py`、`insights.py`、`notify.py`、`plugins.py` 的发布
  门槛全部卡 developer);插件部署即全员可见,无审批环节;无首个管理员的产生机制。

## 决策

1. **角色层级制**(admin ⊃ developer ⊃ user):
   - `role` 仍为单值枚举,新增 `admin`;
   - admin 天然拥有 developer 全部能力,鉴权用层级辅助函数
     (`require_admin()` / `require_developer()`,后者放行 admin+developer),
     不在业务代码中直接比较 `role`;
   - 平台级管理操作(用户管理、LLM 端点、平台通知渠道、全局洞察、发布审批)
     收敛为 `require_admin()`;插件开发类操作(部署/调试/挂载知识库/发布申请)
     保持 `require_developer()`。
2. **首个 admin 由环境变量引导**:`INITIAL_ADMIN_EMAIL`,启动时该邮箱存在则升为
   admin,否则创建(密码取 `INITIAL_ADMIN_PASSWORD` 或随机+日志提示),幂等。
3. **发布审批制**:插件部署后默认 `pending_review`,仅 owner 与 admin 可见/可试;
   admin 审批通过(`approved`)后方对全员可见;admin 可驳回(`rejected`,附原因,
   owner 可改后重新提交)。

## 理由

- 层级制贴合初期"admin 往往自己也开发"的现实,避免 admin 换角色调试插件的别扭;
- 环境变量引导最简单、幂等、不引入额外 CLI 子命令与交互;
- 审批制是平台作为"可信发布方"对普通用户的兜底(LLM 端点、提示词质量、内容安全),
  初期助手数量少,人工审批成本可接受,且是后续付费分层的前置闸门。

## 不做

- 不做正交角色体系(RBAC 表、细粒度 permission 点)——三档层级够用,复杂化留到有需求;
- 不做付费分层(预留"可见性判断收敛于一处"的扩展点,见设计 015 §7);
- 不做插件多版本与审批历史表(A 驳回重提覆盖原记录,保留 last_review_reason 即可)。
