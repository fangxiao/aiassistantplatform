# 任务拆解 · 内容型连接器(M13)

- 文档版本:v0.1
- 日期:2026-09-12
- 流程阶段:阶段 3 · 任务拆解
- 依据:[009-content-connectors](../design/009-content-connectors.md)、[需求 006](../requirements/006-content-connectors.md)

## 依赖关系

```
M13
├─ P0 框架 + 网页连接器
│    ├─ T13.1 数据模型与迁移 ──────────────── 地基
│    ├─ T13.2 adapter 协议 + 网页 adapter(SSRF) ─ 依赖 T13.1
│    ├─ T13.3 同步编排(幂等 upsert/软删/run 记录) ─ 依赖 T13.1, T13.2
│    ├─ T13.4 API(sources CRUD / sync / runs) ──── 依赖 T13.3
│    ├─ T13.5 调度器(轮询 + 启动恢复) ──────── 依赖 T13.3
│    ├─ T13.6 WebUI 数据源管理 ───────────── 依赖 T13.4
│    └─ T13.7 测试(单测/集成/验收) ─────────── 依赖 T13.4
├─ P1:T13.8 github adapter(依赖 T13.3)
└─ P2:T13.9 feishu / T13.10 confluence(依赖 T13.3)
```

## 任务

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T13.1 ✅ | **数据模型与迁移**:`kb_data_sources` / `kb_sync_runs` 两表;kb_documents 加 data_source_id/external_id/external_url(无 FK,删源不删文档);settings 增 connector_* 配置 | - | P0 |
| T13.2 ✅ | **adapter 协议 + 网页 adapter**:`connectors/base.py`(FetchedDoc/FetchResult/ADAPTERS 注册表);`web.py`:种子+sitemap BFS、同 host 过滤、SSRF DNS 级拦截(loopback/private/link-local/reserved)、重定向≤5、robots 默认遵循、单页 5MB、html_cleaner 转 markdown;transport 可注入 | T13.1 | P0 |
| T13.3 ✅ | **同步编排**:`connectors/service.py`:源 CRUD、trigger_sync(202 后台)、run 生命周期、幂等 upsert(新增/更新/跳过)、full 型删除 diff→软删、超限 skip 不中断、同源并发拒绝 | T13.2 | P0 |
| T13.4 ✅ | **API**:`/api/kb/kbs/{id}/sources` CRUD + `/sync`(202)+ `/runs`;can_manage 鉴权;type 白名单;凭据不回显 | T13.3 | P0 |
| T13.5 ✅ | **调度器**:`connectors/scheduler.py` 60s tick 轮询 due 源 + 启动即扫(重启恢复);lifespan 启停;同 source running 拒绝天然防多 worker 重复 | T13.3 | P0 |
| T13.6 ✅ | **WebUI**:kb 页「数据源」区(列表/状态/立即同步/运行历史)+ 新建弹窗(web 表单) | T13.4 | P0 |
| T13.7 ✅ | **测试**:web adapter 单测(SSRF 拦截/同域/markdown/上限,MockTransport);编排幂等(首同步/更新/删除/跳过);API 集成(鉴权/202/凭据不回显);调度 due 判定;需求 006 验收 1/2/4/5/7/8 覆盖 | T13.4 | P0 |
| T13.8 | **github adapter**:repo/分支/路径白名单/后缀过滤,Contents API,commit SHA 增量 | T13.3 | P1 |
| T13.9 | **feishu adapter**:自建应用凭据加密存储,wiki/文件夹枚举,docx→markdown,更新时间增量(full=False) | T13.3 | P2 |
| T13.10 | **confluence adapter**:站点+PAT,空间 CQL,storage XHTML→markdown,version 增量 | T13.3 | P2 |

## 说明

- 已知限制(记入 009 §6/§9):调度器进程内单例,多 worker 重复触发靠 running 拒绝去重;
  分布式锁规模化阶段再做。删除检测仅 full 型 adapter(web/confluence/github)。
- 验收对照:需求 006 §4 全部 8 条;P0 覆盖 1/2/4/5/7/8,3(P1/P2 各 adapter 用例)、
  6(权限)由知识库既有测试 + T13.7 权限同质用例覆盖。
