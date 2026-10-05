# 需求文档 · 认证与账号体系加固(M24 · Auth Hardening)

- 文档版本:v0.3(P1/P2 均已交付;P2 于 20261005 细化并实现,验证状态见设计 018 §10)
- 流程阶段:P1、P2 已收口;P3(治理)未启动

## 1. 背景

平台经 Cloudflare 隧道公网暴露,原"邮箱密码+开放注册+30 天 JWT"不可持续:
暴力破解/撞库无防护、开发者注册摩擦大、CLI 复用登录 JWT 无法独立撤销。

## 2. 分期决策(20261003 用户确认)

- 注册:**邀请码制**(P1)——注册必须持有效邀请码;admin 生成/管理
- **GitHub OAuth 联登**(P1)——开发者零密码注册(仍需邀请码?→ 否:
  GitHub 登录视为已受信渠道,免邀请码,首登自动建号 role=user)
- JWT 双令牌+httpOnly cookie 改造:**P2**(含飞书扫码登录、邮箱验证)
- 治理(设备管理/角色自助申请):P3

## 3. P1 验收标准

- A1 GitHub 登录:登录页「使用 GitHub 登录」→ 授权 → 回调 → 已有同邮箱账号则绑定,否则建号;签发与密码登录同构 JWT
- A2 账号绑定:user_identities 支持一账号多第三方身份;解绑需保留至少一种登录方式
- A3 邀请码:注册必填;码为 admin 生成的限量一次性码(次数+过期);admin 可列表/作废
- A4 PAT:Web 个人设置生成/命名/撤销 CLI 令牌;CLI 端可直接使用;登录 JWT 与 PAT 独立
- A5 限频:login/register 按 IP 5 次/分钟;同账号连续失败 5 次锁 15 分钟;同 IP 注册 3 个/小时
- A6 兼容:存量邮箱密码登录不受影响;存量 config.json token 不失效

## 4. P2 验收标准(20261005 细化,方向已于 20261003 确认)

### B1 JWT 双令牌轮换 + httpOnly cookie

- B1.1 登录(密码/GitHub/飞书)统一签发:access JWT(2h)+ refresh 令牌(30d,`rf_` 前缀,sha256 落库可撤销)
- B1.2 refresh 经 httpOnly Cookie 下发(SameSite=Lax、Path=/api/auth、生产 Secure);access 仍走 Bearer(localStorage)——CLI/Web 认证通道统一,CSRF 面收口到唯一端点
- B1.3 `POST /auth/refresh`:cookie 换新 access+新 refresh(轮换,旧的即废);检测到已轮换令牌重放 → 吊销整个令牌族(该次登录全部设备会话失效)
- B1.4 `POST /auth/logout`:吊销令牌族+清 cookie+前端清 localStorage(平台此前无登出)
- B1.5 兼容(延续 A6):存量 30d JWT 与 PAT 在有效期内继续可用;CLI/PAT 路径零改动
- B1.6 Web 静默续期:API 401 → 自动 refresh 一次并重放原请求;仍失败才跳登录页

### B2 飞书扫码登录

- B2.1 登录页「飞书扫码登录」→ 飞书 passport 扫码授权 → 回调 → 已绑定直登;同邮箱账号绑定;否则免邀请码建号(role=user,与 GitHub 同为受信渠道)
- B2.2 复用默认机器人应用(settings.feishu_app_id/secret);未配置时端点 503
- B2.3 OAuth state 校验(飞书新增;GitHub 顺手补齐)——防 CSRF 授权劫持
- B2.4 飞书侧邮箱可见 → 建号即视为已验证;不可见 → 合成占位邮箱(`@feishu.local` 内部域,不投递),不标记已验证

### B3 邮箱验证

- B3.1 密码注册成功即发验证邮件(24h 有效令牌;SMTP 未配置则跳过不阻断注册)
- B3.2 `POST /auth/verify-email`(邮件链接 → 前端中转)+ `POST /auth/resend-verification`(登录态,限频 1 次/分钟、3 次/天)
- B3.3 GitHub/飞书登录建号:邮箱即已验证(受信 IdP);存量用户回填:已有第三方身份绑定的视为已验证
- B3.4 力度:**横幅提醒可关闭,不硬阻断功能**(阻断策略留 P3 评估)——邀请码+受信联登已控注册质量,横幅保底找回能力
- B3.5 admin 用户列表可见验证状态

## 5. 范围外(P3)

- 设备管理(会话列表/主动踢出)、角色自助申请流、登录异常通知
- 未验证邮箱的差异化限制(如禁 deploy)与强制验证策略
- 限频存储从进程内换 Redis(多实例前置)
