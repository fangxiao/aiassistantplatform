# 009 · 内容型连接器设计

- 文档版本:v0.1
- 日期:2026-09-12
- 流程阶段:阶段 2 · 设计
- 对应需求:[../requirements/006-content-connectors.md](../requirements/006-content-connectors.md)
- 关联:008-knowledge-base(连接器是知识库的数据入口)、ADR 0004/0005/0006
- 里程碑:M13

---

## 1. 架构总览

连接器只负责"取内容 + 产出标准化文档",解析/切分/向量化/检索/权限全部复用知识库
既有管线。框架与 adapter 分离:同步编排、幂等、删除处理、调度只做一次。

```
api/kb.py(/sources CRUD /sync /runs)
      │
      ▼
core/kb/connectors/service.py ── 编排:run 记录 → adapter.fetch → 幂等 upsert/软删 → 汇总
      │                                   │
      │                     adapters 注册表 {type: fetch_fn}
      │                                   │
scheduler.py(60s tick 轮询) ──►        ▼
(启动扫描恢复)                 web.py  github.py(P1)  feishu.py(P2)  confluence.py(P2)
                                       │
                                       ▼
                        FetchedDoc(external_id/url/title/markdown)
                                       │
core/kb/service._create_document(溯源 origin="connector") ─► pipeline(解析/切分/向量化,现成)
```

## 2. 数据模型

**kb_data_sources**(数据源)

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid pk | |
| kb_id | fk knowledge_bases CASCADE | 目标库 |
| type | text | web / feishu / confluence / github(校验白名单) |
| name | text | 展示名 |
| config | jsonb | 明文配置(urls/sitemap/depth/max_pages/repo 路径等,按 type 定 schema) |
| credentials_enc | text nullable | 密文(复用 core/llm/crypto;web 无凭据为空);API 永不回显 |
| poll_interval_minutes | int nullable | null=仅手动;60/1440… 轮询间隔 |
| status | text | active / disabled(disabled 不参与调度,可手动同步) |
| last_sync_at / last_status / last_error | | 最近一次同步结果(never/running/success/failed/partial) |
| created_at / updated_at | timestamptz | |

**kb_sync_runs**(运行记录)

| 字段 | 说明 |
|---|---|
| id, data_source_id fk CASCADE, started_at, finished_at | |
| status | running / success / failed / partial(有跳过或单文档失败) |
| added / updated / deleted / skipped / failed_docs | 计数(skipped=未变更或 hash 重复) |
| error | 摘要错误(failed/partial 时) |

**kb_documents 增列**(迁移):`data_source_id uuid nullable`(无 FK 约束——删除数据源不删文档,
需求 U8)、`external_id text nullable`(外部文档幂等键;web=规范化 URL)、
`external_url text nullable`(溯源:检索结果可点开原文)。索引 (data_source_id, external_id)。
溯源语义:origin="connector",source_app=数据源 type。

## 3. Adapter 协议

```python
@dataclass(frozen=True)
class FetchedDoc:
    external_id: str      # 幂等键(web 为规范化 URL,去 fragment)
    url: str              # 原文链接(溯源)
    title: str
    content_markdown: str
    mime: str = "text/markdown"

@dataclass(frozen=True)
class FetchResult:
    docs: list[FetchedDoc]
    full: bool            # True=全量枚举(支持删除检测);False=增量不可判删

async def fetch(config: dict, credentials: dict, *, transport=None) -> FetchResult
```

- adapter 为纯函数模块,网络经由可注入 `transport`(httpx.MockTransport 测试用);
  adapter 内不做 DB 操作,产出内存 FetchResult 即可。
- 注册表 `ADAPTERS: dict[str, fetch_fn]`;未注册 type 建源时拒绝。
- 删除检测:full=True 时,orchestrator 将该 source 下现有(未删)文档 external_id
  与本次集合 diff → 软删(web/confluence/github 全量型);full=False 只增改(feishu 增量型)。

## 4. 幂等与更新策略(orchestrator)

对每个 FetchedDoc,查 `(data_source_id, external_id, status != deleted)`:

1. 不存在 → `service._create_document` 落库(origin="connector";跳过 can_write——
   触发者已过 can_manage;保留大小/数量/hash 校验,超限计 skipped 不中断,需求验收 7);
   content_hash 命中同库既有文档(未删)→ skipped;
2. 存在且 hash 相同 → skipped(未变更,不重复建 chunk);
3. 存在且 hash 不同 → 覆写文件与 size_bytes/content_hash,status=pending 入队重新处理(updated);
4. full 同步 diff 出的外部已删文档 → 物理删 chunks + status=deleted,统计回写(deleted)。

同步以 `(source, run)` 串行;同 source 已有 running run 时拒绝再次触发(防并发重入)。
run 全程独立 Session;单文档失败计 failed_docs 继续(run=partial),fetch 整体异常 → run=failed。

## 5. 网页 adapter(web.py)

- 配置:`{urls: [种子], sitemap?: url, max_depth=2, max_pages=200, respect_robots=true}`
- BFS 抓取:种子 URL + sitemap.xml 展开;同 host 判定(精确 host 匹配,防子域扩散);
  只收 `text/html`;链接提取用 html.parser;深度/页数/单页 5MB 上限。
- **SSRF 防护**:仅 http/https;每跳手动跟随(≤5 次重定向),对每跳目标做 DNS 解析,
  拒绝 loopback / private / link-local(含 169.254.169.254 云元数据)/ reserved / multicast;
  域名解析失败即拒绝。
- robots.txt:默认遵循(urllib.robotparser,per-host 缓存);config 可关。
- 正文:`html_cleaner.run()`(平台内置同一实现,本地 dev 与平台行为一致)→
  `{title, cleaned_markdown}`;markdown 直接入库(mime=text/markdown)。
- external_id = URL 规范化(去 fragment,统一 https? 与尾斜杠不敏感——保留 scheme 差异,
  仅去 fragment 与空白);filename = 标题或 URL 尾段 slug + `.md`。

## 6. 调度器(scheduler.py)

- asyncio 后台任务,`settings.connector_scheduler_tick_seconds`(60s)tick:
  扫 `status=active AND poll_interval_minutes IS NOT NULL` 且
  `last_sync_at IS NULL OR now-last_sync_at >= interval` 的 source → 逐个触发同步
  (异常捕获记日志,不影响其他 source)。
- 启动时即刻扫一轮(重启恢复,验收 4);进程内单例,stop 由 lifespan 管理。
- 已知限制(同 BrowserBridge):多 worker 各自持有调度器会重复触发——
  靠"同 source 已有 running run 拒绝"天然去重;分布式锁留待规模化。

## 7. API(风格沿用 005/008)

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/kb/kbs/{kb_id}/sources` | 列表 / 新建(can_manage;type 白名单校验) |
| PATCH/DELETE | `/api/kb/kbs/{kb_id}/sources/{sid}` | 改配置/启停 / 删除(文档保留) |
| POST | `/api/kb/kbs/{kb_id}/sources/{sid}/sync` | 立即同步 → 202 {run_id}(后台执行) |
| GET | `/api/kb/kbs/{kb_id}/sources/{sid}/runs?limit=10` | 运行记录倒序 |

响应不含 credentials_enc;错误统一 {error:{code,message}}。

## 8. WebUI(kb 管理页)

库详情新增「数据源」区:源列表(类型徽标/名称/轮询/最近状态圆点/最近同步时间/
立即同步/展开最近运行)、新建弹窗(web 表单:名称、种子 URL 多行、sitemap、深度、
页数上限、轮询 关/每小时/每天)、同步中轮询 runs 刷新状态。

## 9. 安全与风险

| 风险 | 缓解 |
|---|---|
| SSRF(内网探测/云元数据) | §5 DNS 级拦截 + 协议白名单 + 重定向上限 |
| 恶意大页面拖垮 | 单页 5MB、页数上限、总超时、并发 4 |
| robots 侵权 | 默认遵循 robots.txt;可关但记录在 config(审计留痕) |
| 凭据泄露 | 密文存储、API 不回显、错误信息不含凭据 |
| 同步风暴 | 同 source 串行 + running 拒绝;调度 tick 去重 |
| prompt 注入 | 复用 008 §9 引用块包裹(kb_search 层,已有) |

## 10. 分期与后续

- **P0(本设计已覆盖)**:框架 + web adapter + API + 调度器 + WebUI + 测试。
- **P1**:github adapter(commit SHA 增量);轮询调度实测。
- **P2**:feishu(app_id/secret + wiki/docx API)、confluence(CQL + XHTML→md)。
- 动作型/通道型连接器、源 ACL 继承、Webhook 见需求 006 §6 范围外。
