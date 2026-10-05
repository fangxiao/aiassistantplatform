# 任务拆解 · M24 P2 认证加固二阶段(对应需求 013 §4 / 设计 018 §5-§9)

- 日期:2026-10-05
- 流程阶段:阶段 3 · 任务拆解(当日实现收口)
- 前置:P1 已交付(e8438c0 等)

## 任务清单

| # | 任务 | 依赖 | 产出 | 状态 |
|---|---|---|---|---|
| P2.1 | alembic 迁移:`users.email_verified_at` + `refresh_tokens` 表 + 存量绑定用户回填 | — | migration `d8f3a1c6b9e2` | ✅ 20261005 |
| P2.2 | 令牌层:core/auth/tokens.py(access 2h `typ:"access"` / refresh 签发/轮换/家族吊销 / 邮箱验证令牌);service 转出口保旧导入路径 | P2.1 | core/auth/tokens | ✅ 20261005 |
| P2.3 | 会话端点:`issue_session` 统一签发(login/OAuth 回调接线)+ `POST /auth/refresh` + `POST /auth/logout` + cookie 工具(HttpOnly/Lax/Path=/api/auth/https 加 Secure) | P2.2 | api/auth_session + auth | ✅ 20261005 |
| P2.4 | 邮箱验证:令牌签发/校验、`/auth/verify-email`(幂等)、`/auth/resend-verification`(1/min、3/day)、注册线程投递(SMTP 未配跳过)、`UserOut.email_verified`、`public_web_base` 配置 | P2.1 | api + notify 复用 | ✅ 20261005 |
| P2.5 | 飞书扫码:state 签发/校验(短 cookie,GitHub 同套补齐)、`/auth/feishu` + callback(v2 换 token + v1 user_info)、`oauth_upsert_user` 公共化、GitHub 回调改造接线 | P2.2 | api/auth_ext | ✅ 20261005 |
| P2.6 | web:client 401 静默刷新+单飞+重放;登录页飞书按钮与新错误文案;未验证横幅(Navbar,会话级可关);开发者中心邮箱验证卡片+重发;登出改走 `/auth/logout`;`verify_token` 回调落地;admin 用户列表「未验证」标记 | P2.3,P2.4 | web | ✅ 20261005 |
| P2.7 | 测试:test_auth_p2 14 用例(轮换/重放吊销/legacy 兼容/cookie 属性/state/邮箱验证/飞书 mock 含无邮箱占位)+ 限频锁定语义回归修正用例;全量 pytest 403 绿;web tsc+vitest 绿 | P2.2-P2.5 | pytest | ✅ 20261005 |
| P2.8 | 部署 + 冒烟:`compose up --build` + `alembic upgrade head`;live 实测登录双令牌/cookie 属性/轮换/重放吊销/登出失效/锁定语义/飞书 302+state/坏 state 拒绝/邮箱验证落库/web 200 | P2.7 | 验证记录(设计 018 落地记录) | ✅ 20261005 |
| P2.9 | 文档同步:需求 013 v0.2、设计 018 落地记录、部署配置清单(SMTP/飞书白名单/public_web_base) | P2.8 | docs | ✅ 20261005 |

## 依赖关系

```
P2.1 ── P2.2 ──┬── P2.3 ──┐
               ├── P2.5 ──┼── P2.6 ── P2.7 ── P2.8 ── P2.9
        P2.4 ──┘──────────┘
```

## 验收对齐需求 013:B1(双令牌/cookie/静默续期/兼容)、B2(飞书扫码/state/占位邮箱)、B3(验证邮件/重发/回填/横幅)

## 落地记录(2026-10-05)

- 顺手修复 P1 缺陷:账号锁定曾写为「任一次失败即锁 15 分钟」(测试只断言了 5 次锁定、未断言 1-4 次不锁);现改为 5 分钟计数窗 + 第 5 次起锁 15 分钟,补回归用例
- cookie 挂载坑:发起 OAuth 的端点若在注入的 `response` 参数上 set_cookie 而返回自建 RedirectResponse,cookie 会被丢弃——state cookie 直接挂在最终响应上
- web 静默刷新:并发 401 共享单次 refresh(单飞),防两请求同时用同一已轮换 cookie 触发全族吊销
- 公网启用前的运营配置项(代码已支持,缺省不启用):GITHUB_CLIENT_ID/SECRET、SMTP(NOTIFY_SMTP_*)、PUBLIC_WEB_BASE;飞书侧需在开放平台「安全设置→重定向 URL 白名单」登记回调地址
- 飞书真实扫码全链与验证邮件真实收信待公网配置后补验(本地冒烟已覆盖 302/state 守卫/回调上游逻辑单测)
