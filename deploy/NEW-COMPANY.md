# 新公司部署操作卡片(场景 A:每公司独立一套)

> 目标:30 分钟内给一家新公司跑起独立平台,配置其专属大模型,初始化管理员。
> 所有数据(知识库/会话/代码归档)留在该公司内网,互不相通。

## 0. 前置确认

- [ ] 目标服务器:Docker + compose 可用,可访问该公司的模型网关/供应商 API
- [ ] 拿到该公司的大模型信息:Base URL、API Key、默认模型名(OpenAI 兼容格式)
- [ ] (可选)内网 GitLab 地址 + read_api 权限的 PAT(离职归档用)
- [ ] (可选)飞书自建应用 app_id/secret(文档同步用)

## 1. 部署(一条命令)

```bash
git clone <平台仓库> && cd agentplatform
./deploy/deploy.sh            # 四容器:pg + redis + api + web;SECRET_KEY 自动生成
./deploy/deploy.sh --with-search   # 如需免费联网搜索(SearXNG + WARP,需能出公网)
```

## 2. 配置该公司的模型(两种方式任选)

**方式一(推荐,部署时)**:写入 `.deploy.env` 后重启 api

```bash
cat >> .deploy.env << 'EOF'
OPENAI_BASE_URL=https://api.该公司网关或供应商/v1
OPENAI_API_KEY=sk-xxxxx
DEFAULT_MODEL=glm-5.3-flash
MULTIMODAL_MODEL=含视觉能力的模型名
EOF
docker compose up -d api
```

**方式二(运行时,管理员操作)**:注册首个账号 → 数据库提升 developer(见 §3)→
开发者中心 → LLM 端点 → 添加平台共享端点(该公司全员可用)。

多供应商:方式二可加多个端点(不同模型名各行其是,模型目录自动聚合);
用户还能在「我的模型」加个人端点(个人 key 仅本人)。

## 3. 初始化管理员(首个 developer)

注册接口默认只允许普通 user(防自提权),首个管理员用 SQL 提升:

```bash
docker compose exec -T pg psql -U agentplatform -d agentplatform -c \
  "UPDATE users SET role='developer' WHERE email='管理员邮箱';"
```

该公司后续的管理员由现有 developer 在库内直接改(或保持 SQL)。

## 4. 部署验收

- [ ] 打开 `http://<server>:3000` 能登录
- [ ] `http://<server>:3000/status` 诊断六项全绿(LLM/Embedding 必须 ✅)
- [ ] 发一句对话验证模型网关连通
- [ ] (配了 GitLab)知识库 → 添加数据源 → 🦊 GitLab → 同步成功

## 5. 常见问题

| 症状 | 处理 |
|---|---|
| LLM 诊断 ❌ | 检查 .deploy.env 是否生效(environment 空值会覆盖 env_file——已在 compose 修复,旧部署需拉新版) |
| Embedding ❌ | 需 embedding 端点:开发者中心加 `endpoint_type=embedding` 的端点(如 Ollama bge-m3),或 .env 设 KB_EMBEDDING_MODEL 走主网关 |
| 公司网络不能出公网 | SearXNG 搜索与飞书推送不可用;GitLab 同步不受影响(内网) |
| 忘记管理员 | 同 §3 的 SQL 语句 |
| 备份 | `./deploy/backup.sh`(建议 crontab 每日) |

## 6. 该公司员工的自助能力

- 任何注册用户:对话(用公司模型)、建私有库、我的模型(个人端点)、定时任务、通知通道
- developer:平台共享端点、洞察面板(成本/用户/动作审计)、数据源管理
