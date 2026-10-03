# 技术设计 · 认证加固(018 · 对应需求 013)

## 1. 数据模型(迁移 c7d2e8f1a430)

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
