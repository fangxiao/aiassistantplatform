# 技术设计 · 模型供应商管理(023 · 对应需求 018)

- 文档版本:v0.1(20261008,与需求 018 同轮,方向确认中)
- 关联:001-architecture(LLM 网关)、004-data-model(llm_endpoints)

## 1. 核心决策:供应商表 + 端点挂靠,路由零改动

`resolve_endpoint(model, user_id)` 按 (owner, model) 精确匹配的路由机制**不动**——
供应商只是端点的组织层:

```
llm_providers(id, user_id, name, preset, base_url, api_key_enc,
              status: verified|unverified|invalid, last_checked_at, created_at)
llm_endpoints 增 provider_id nullable(指向我的供应商)
```

模型仍存 llm_endpoints(一行一模型,owner 归属),`resolve_endpoint` 无需感知
供应商;删除供应商级联删其端点。

## 2. 供应商预设(设计 023 常量)

| preset | base_url 预填 | 备注 |
|---|---|---|
| volcark | https://ark.cn-beijing.volces.com/api/v3 | 火山方舟 |
| deepseek | https://api.deepseek.com/v1 | |
| siliconflow | https://api.siliconflow.cn/v1 | 硅基流动 |
| openai | https://api.openai.com/v1 | |
| anthropic | https://api.anthropic.com/v1 | 兼容层/网关转发 |
| custom | 空 | 手填 |

## 3. 验证与模型发现

`POST /llm/providers` / `PATCH .../key` 时(后台 5s 超时):

```
GET {base_url}/models  (Authorization: Bearer <key>)
200 → status=verified, 返回模型 id 列表(前端勾选入库)
非 200/超时 → status=unverified(可保存),提示原因(401=key 错)
```

模型列表不落库缓存(每次添加/换 Key 时现拉;列表页展开可重拉)。

## 4. API(prefix /llm,owner 隔离)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/llm/providers` | 列表(含模型数/状态)/新建(带验证+模型发现) |
| PATCH | `/llm/providers/{id}` | 改名/换 Key(重验证)/启停 |
| DELETE | `/llm/providers/{id}` | 级联删端点(模型选择器即时消失) |
| POST | `/llm/providers/{id}/models` | 勾选落库(全量覆盖该供应商模型集) |
| GET | `/llm/providers/{id}/models` | 重拉上游列表(不落库,返回候选) |
| GET | `/llm/models` | 升级:响应增 provider 分组信息 |

`/llm/auto-pool` 与会话 `model_override` 机制不变。

## 5. 前端

- **会话模型下拉**(聊天页头部,现 auto 池下拉升级):
  分组「平台网关」(auto + 池)/「我的供应商」(按供应商分组,其勾选模型)/
  「平台共享」;底部 `+ 添加自定义供应商` → 添加弹窗(预设选择 → key →
  验证动画 → 模型勾选列表 → 保存)
- **MyModelsPanel 升级**(开发者中心):供应商卡片(状态徽标/模型数/测试/编辑/
  删除),保留原端点列表为「导入的端点」区
- Key 输入框 password 态,编辑时不回显(占位符「已配置」)

## 6. 迁移与兼容

- 迁移:llm_providers 表 + llm_endpoints.provider_id 列;存量个人端点(owner 非
  null 且非 admin 共享)每条生成「导入的端点」供应商(preset=custom,status=
  verified——既存可用),端点挂靠
- admin 共享端点(provider_id 空)不受影响
- 助手 manifest.model、CLI、会话 model_override 全部无感(resolve 不变)

## 7. 测试要点

- 供应商 CRUD + owner 隔离;Key 加密不回显
- 验证流:200/401/超时三态(mock 上游);unverified 可保存
- 模型勾选全量覆盖;删除供应商级联;存量端点迁移幂等
- `/llm/models` 分组;会话选自定义模型 → make_llm_client 命中该端点(E2E)
- web vitest:下拉分组渲染/添加弹窗状态机/Key 不回显
