# 技术设计 · 认证加固(018 · 对应需求 013)

> P1 已交付(GitHub 联登/邀请码/PAT/限频)。以下 §5-§9 为 P2(双令牌+飞书扫码+邮箱验证)。

## 1. 数据模型(迁移 c7d2e8f1a430,P1)

- `user_identities(id, user_id FK, provider, provider_uid, created_at)`
  unique(provider, provider_uid)——一账号多身份
- `personal_access_tokens(id, user_id, name, token_hash, prefix, created_at, last_used_at, revoked_at)`
  明文令牌仅创建响应展示一次;`prefix` 前 8 位供列表识别
- `invite_codes(id, code, max_uses, used_count, expires_at, created_by, disabled)`
  一次性语义由 max_uses=1 实现;admin 批量生成

## 2. 认证流

### GitHub OAuth(P1)
```
GET  /api/auth/github                     → 302 github.com/login/oauth/authorize
GET  /api/auth/github/callback?code=      → 换 access_token → GET /user + /user/emails(primary)
    邮箱命中现有账号 → 建 identity 绑定
    未命中 → 建号(role=user) + identity(免邀请码:GitHub 为受信渠道)
    → 302 /auth?token=<jwt>(前端存 localStorage,同现有登录态)
```
- settings:`github_client_id/github_client_secret`(缺失时端点 503 提示未配置)
- 邮箱不可见(私有)且无 primary → 要求 GitHub 侧公开邮箱或回落注册

### 邀请码注册
- `POST /auth/register` 增加 `invite_code` 必填;事务内校验+核销(used_count+1)

### PAT
- `POST /auth/pat {name}` → `ap_<secrets32>`(展示一次;库存 sha256)
- 认证中间件:get_current_user 先解析 JWT,失败则查 PAT(last_used_at 更新节流)
- `DELETE /auth/pat/{id}` 撤销;`GET /auth/pat` 列表(仅 prefix+name+时间)

### 限频
- 进程内滑窗 `{ip: deque}`;login/register 共用;账号失败计数 `{email: (count, until)}`
- 超限 429;单实例足够(trial),多实例时换 Redis(P3)

## 3. 前端

- `/auth`:「使用 GitHub 登录」按钮(直跳 /api/auth/github);注册表单加邀请码;回调 token 参数自动落地
- 个人设置(Navbar 下拉 → 设置页新分区):PAT 列表/生成/撤销

## 4. GitHub OAuth App 创建

GitHub 不提供 OAuth App 的创建 API(仅网页),创建路径(60 秒):
github.com → Settings → Developer settings → OAuth Apps → New
- Application name: AgentPlatform
- Homepage: https://ai-web.ailearning.top
- Callback: https://ai-api.ailearning.top/api/auth/github/callback
生成后 Client ID/Secret 交平台配置(.deploy.env: GITHUB_CLIENT_ID/SECRET)

---

# P2 设计(双令牌 + 飞书扫码 + 邮箱验证)

## 5. 数据模型(迁移 P2)

- `users.email_verified_at`(timestamptz 可空)——非空即已验证
- 新表 `refresh_tokens`:
  `id uuid pk / user_id FK / family_id uuid / token_hash str(64) unique / created_at / expires_at / revoked_at / last_used_at / user_agent str / ip str`
  - 明文 `rf_<secrets43>` 仅出现于 cookie;库存 sha256
  - `family_id`:一次登录的整条轮换链;重放已轮换令牌 → 按 family 吊销全链
- 存量回填(数据迁移):有 user_identities 绑定的用户 `email_verified_at=now()`,其余留空(横幅引导)

## 6. 双令牌与 Cookie

### 令牌形态

| | access | refresh |
|---|---|---|
| 形态 | JWT HS256(claim 增 `typ:"access"`) | 不透明随机串 `rf_` |
| 寿命 | **2h** | **30d**(与旧 JWT 用户可感周期一致) |
| 存储 | 前端 localStorage(CLI 兼容 Bearer) | httpOnly Cookie(不落 JS) |
| 吊销 | 自然过期 | DB 行 revoked_at / family 吊销 |

- 签发入口统一:`_issue_session(user, response)` = access + refresh(cookie) + TokenOut
- 旧 JWT(无 `typ` claim)按 legacy 接受至自然过期;PAT 路径不变

### Cookie 属性

`Set-Cookie: rf=<token>; HttpOnly; SameSite=Lax; Path=/api/auth; Max-Age=30d; Secure(生产)`
- web(ai-web)↔ api(ai-api)同父域 ailearning.top → same-site,`Lax` 下 fetch 正常携带;localhost:3000↔8000 同理
- 不设 Domain(host-only,降低别的子域误读面);Path 收窄到 /api/auth,业务 API 永不带此 cookie
- CORS 已是显式 origin 列表 + allow_credentials=True,无需改

### 端点

```
POST /auth/refresh   仅凭 cookie;校验→旧 token 标记 rotated(revoked_at)→ 若已 revoked 即重放
                     → 吊销该 family 全部 → 401;正常则签发新对(同 family)
POST /auth/logout    吊销 family + Set-Cookie 清除;前端另清 localStorage
```

- 登录类端点(login/register/oauth callback)全部改走 `_issue_session`
- web client 封装:401 → 单飞(singleton promise)调 refresh → 重放原请求一次;SSE 流 401 不重放直接跳登录

## 7. 飞书扫码登录

```
GET /api/auth/feishu           → 302 passport.feishu.cn/suite/passport/oauth/2.0/authorize
                                 ?client_id={app_id}&redirect_uri={public_api_base}/api/auth/feishu/callback
                                 &response_type=code&state={signed_state}
GET /api/auth/feishu/callback  → 校验 state(cookie 对照)
                                 → POST open.feishu.cn/open-apis/authen/v2/oauth/token (authorization_code)
                                 → GET  open.feishu.cn/open-apis/authen/v1/user_info (user_access_token)
                                 → 身份落库逻辑与 GitHub 完全共用(§8 重构出的公共函数)
```

- `provider="feishu"`,uid 优先 `union_id`(换应用稳定)回落 `open_id`
- 邮箱:`user_info.email`/`enterprise_email` 命中现有账号 → 绑定;无绑定但有邮箱 → 建号+已验证;无邮箱 → 建号 `{uid 前 16}@feishu.local`(内部域)+ 未验证
- 应用前提(部署文档同步):开放平台该应用开启「安全设置 → 重定向 URL 白名单」加回调地址;网页授权能力默认可用
- state:短期(5min)签名串,`/api/auth/{github,feishu}` 签发写短 cookie,回调比对;GitHub 同套补齐

## 8. GitHub 流小重构

- 抽公共 `oauth_upsert_user(session, provider, uid, email, email_verified)`(查 identity→查邮箱→建号),GitHub/飞书共用;github_callback 保留换 token 部分
- 建号默认 `email_verified_at=now()`(GitHub 邮箱受信);回调统一 `_issue_session` 下发双令牌

## 9. 邮箱验证

- 令牌:JWT `{sub, typ:"email_verify", exp:24h}`,不落库
- 注册(密码)成功 → `send_email`(复用 notify SMTP,线程投递防阻塞;未配置跳过+日志)
  邮件链接:`{public_web_base}/auth?verify_token=...` → 前端 onLoad `POST /auth/verify-email {token}`
- `POST /auth/resend-verification`:登录态 + 进程内限频(1/min、3/day per user)
- `UserOut` 增 `email_verified: bool`;web 顶栏横幅(未验证且邮箱可投递时显示,可关,sessionStorage 记忆);设置页显示状态+重发;admin 用户列表加列
- 新配置:`public_web_base`(默认 http://localhost:3000,邮件链接用)

## 11. P3 落地记录(2026-10-06,裁剪版见需求 013 §6-§7)

- 设备管理:tokens.list_login_sessions 按族聚合(活跃=未吊销未过期;历史取 10);
  revoke_family_by_id 校验属主;web「登录设备」卡(下线+登录记录=C2 知情降级)
- 测试:auth 16/16;live 冒烟 列表→下线→refresh 401 全过
- deferred 项与理由:需求 013 §7

## 10. P2 落地记录(2026-10-05)

- 迁移 `d8f3a1c6b9e2`(users.email_verified_at + refresh_tokens + 绑定用户回填);全量 pytest 403 绿(新增 test_auth_p2 14 用例),web tsc/vitest 绿
- 实现与 §5-§9 一致,偏差三处:
  1. GitHub/飞书发起端点的 state cookie 直接挂最终 RedirectResponse(FastAPI 注入 response 参数对自建响应不生效,实测踩坑)
  2. 飞书无邮箱占位:`fs-{union_id 前 16}@feishu.local`,与 §7 设计一致
  3. admin 用户列表验证状态以「未验证」徽标呈现(B3.5)
- live 冒烟:登录双令牌(cookie 属性逐项核对)/ refresh 轮换 / 重放旧 cookie → 401 且新 cookie 全族失效 / logout 后 refresh 401 / 锁定语义(1-4 次不锁,第 5 次锁) / 飞书 302 passport + state cookie / 坏 state → error=oauth_state / 邮箱验证端点落库 / web /auth 200
- 公网启用清单(缺省不启用,配 .deploy.env):
  - OAuth:`PUBLIC_API_BASE=https://ai-api.ailearning.top`、`PUBLIC_WEB_BASE=https://ai-web.ailearning.top`、`GITHUB_CLIENT_ID/SECRET`(P1 §4 建 App)
  - 飞书:开放平台「安全设置 → 重定向 URL 白名单」加 `https://ai-api.ailearning.top/api/auth/feishu/callback`(本地调试另加 `http://localhost:8000/...`);复用机器人 FEISHU_APP_ID/SECRET
  - 邮件:`NOTIFY_SMTP_HOST/PORT/USER/PASS`(+可选 NOTIFY_FROM)
- P1 缺陷顺带修复:账号锁定误写为一次失败即锁(现 5 分钟计数窗内 5 次才锁),已补回归用例
- 待公网补验:飞书真实扫码建号全链、验证邮件真实收信
