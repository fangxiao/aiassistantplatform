# 任务拆解 · 知识库(005/008 落地)

- 文档版本:v0.1
- 日期:2026-09-05
- 流程阶段:阶段 3 · 任务拆解(增量)
- 依据:[008-knowledge-base.md](../design/008-knowledge-base.md) · 需求 [005-knowledge-base.md](../requirements/005-knowledge-base.md) · ADR 0004/0005
- 里程碑命名:M12 · 知识库

---

## 1. 概述

基于设计 008,拆解为 M12 里程碑共 14 个任务。核心闭环(T12.1→T12.7→T12.14)是:建表 → pipeline 向量化 → `tool:kb_search` 检索(权限收口)→ 验收测试。

优先级:
- **P0**:数据模型、embedding、pipeline、检索与权限、注册表集成、验收测试
- **P1**:WebUI(管理页 + 会话挂载入口;P0 期间经 API/CLI 可演示核心闭环)

工程约束(沿既有实践):uv 单项目、Alembic 迁移、真实 PG 测试库(不可达自动 skip)、错误统一 `{error:{code,message}}`。

---

## 2. 依赖关系总览

```
M12(知识库)
├─ T12.1 数据模型迁移(pgvector + 三表 + kind 扩展) ──── P0,地基
├─ T12.2 core/kb/model.py ORM ───────────────────────── P0,依赖 T12.1
├─ T12.3 core/kb/service.py 库 CRUD/鉴权/配额 ────────── P0,依赖 T12.2, M1
├─ T12.4 embedding 端点(llm_endpoints 扩展 + embed 客户端) ─ P0,依赖 T12.1, M3
├─ T12.5 core/kb/pipeline.py 处理状态机 ──────────────── P0,依赖 T12.2, T12.4
├─ T12.6 core/kb/retriever.py pgvector 检索后端 ──────── P0,依赖 T12.1, T12.4
├─ T12.7 tool:kb_search 内置工具 + 会话范围组装 ──────── P0,依赖 T12.6, M5
│    └─ (依赖 T12.9/T12.10 完成后范围含插件依赖库与用户挂载库)
├─ T12.8 api/kb.py REST ─────────────────────────────── P0,依赖 T12.3/T12.5/T12.6
├─ T12.9 公共库发布 + skill_tools kind=kb 登记 ───────── P0,依赖 T12.3, M2
├─ T12.10 会话挂载 sessions.mounted_kb_ids ───────────── P0,依赖 T12.3
├─ T12.11 CLI validate kb: 依赖校验 ─────────────────── P0,依赖 T12.9
├─ T12.12 WebUI 知识库管理页 ✅ ──────────────────────── P1,依赖 T12.8, M8
├─ T12.13 WebUI 会话挂载入口 ✅ ──────────────────────── P1,依赖 T12.10, M8
└─ T12.14 测试:单测 + 5 条验收集成 ──────────────────── P0,依赖 T12.7
```

---

## 3. 里程碑与任务

### M12 · 知识库(P0)

| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T12.1 | **数据模型迁移**:启用 pgvector 扩展;`knowledge_bases` / `kb_documents` / `kb_chunks`(embedding 维度默认 1024,HNSW cosine + kb_id 索引);`skill_tools.kind` 枚举加 `kb`(ALTER TYPE);`llm_endpoints.endpoint_type`(chat/embedding);`sessions.mounted_kb_ids` jsonb | M0.4, M2.1 | P0 |
| T12.2 | **ORM 模型** `core/kb/model.py`:三表模型,软删文档以 `kb_documents.status=deleted` 表达 | T12.1 | P0 |
| T12.3 | **库服务** `core/kb/service.py`:库 CRUD、可见性判定(private=owner / public=全员读、管理员写)、文档增删(hash 去重)、配额校验(单文档 20MB / 单库 200 文档,常量可配) | T12.2, M1 | P0 |
| T12.4 | **embedding 端点**:llm 网关支持 `endpoint_type=embedding` 的端点配置与密钥复用;`embed(texts: list[str]) -> list[vector]` 批量客户端(批 64);默认端点选择机制 | T12.1, M3 | P0 |
| T12.5 | **处理 pipeline** `core/kb/pipeline.py`:`pending→parsing→embedding→ready` 状态机;md/txt 直读、pdf 解析(复用 pdf_parse 逻辑,页数上限);~512 token 切分 + 50 重叠 + 段落边界;`source_span` 字符偏移记录;asyncio.Queue 串行 + 启动扫描非 ready 重入队;失败落 `error` 可重试 | T12.2, T12.4 | P0 |
| T12.6 | **检索后端** `core/kb/retriever.py`:Retriever 接口 + PgVectorRetriever(cosine,join 过滤 deleted);按 kb_id 白名单过滤;P95 ≤ 800ms(5 万 chunk)基线 | T12.1, T12.4 | P0 |
| T12.7 | **`tool:kb_search` 内置工具**:`core/kb/search_tool.py` 执行器(builtin 登记,模式同 pdf_parse);参数 query/kb_ids/top_k;**allowed_kb_ids 组装**(chat 侧:mounted ∪ 插件依赖解析,参数 kb_ids 仅做交集筛选);空结果带 hint;依赖 kb 的插件自动注入检索引导 prompt;溯源字段全量返回 | T12.6, M5 | P0 |
| T12.8 | **REST API** `api/kb.py`:008 §7 九个端点,统一响应信封与错误码;检索测试接口走同一鉴权 | T12.3, T12.5, T12.6 | P0 |
| T12.9 | **公共库发布**:`POST /api/kbs/{id}/publish`(管理员,bump semver);事务内登记 `skill_tools(id=kb:<slug>, kind=kb, source=shared, schema={embedding_model, chunk_size})`;`registry` 输出 kb 行文案 | T12.3, M2 | P0 |
| T12.10 | **会话挂载**:`POST/PATCH /api/sessions` 支持 `mounted_kb_ids`;服务端校验每个 id 对当前用户可读;与插件依赖去重 | T12.3, M6 | P0 |
| T12.11 | **CLI validate**:`kb:` 依赖必须带版本约束的校验项;错误提示结构化 | T12.9, M9 | P0 |
| T12.12 ✅ | **WebUI 知识库管理页**:库列表(个人+公共)、新建、文档列表(状态/错误/重试/删除)、上传、检索测试框 | T12.8, M8 | P1 |
| T12.13 ✅ | **WebUI 会话挂载入口**:会话侧栏勾选可读库,写入 mounted_kb_ids | T12.10, M8 | P1 |
| T12.14 | **测试**:service 鉴权/配额、pipeline 状态机与重试、retriever 过滤、search_tool 权限交集(含跨用户 private 拒绝)、validate;集成测试覆盖需求 005 §5 五条验收(真实 PG,不可达 skip) | T12.7 | P0 |
| T12.15 ✅ | **会话产出入库**(设计 008 §11 增补):kb_documents 溯源字段(origin/source_app/source_session_id/source_message_id);`POST /documents/from-text` 文本直存 + 消息级幂等;pipeline 支持 text/html 去标签;KbOut.can_write;WebUI 助手消息「收藏到知识库」;跨项目消费方(SwiftShip)走用户 token 绑定 | T12.3, T12.5, T12.8 | P1 |
| T12.16 ✅ | **shared 可见性与成员管理**(设计 008 §12 增补):kb_visibility 增加 shared(团队资产,不进注册表,publish 拒绝);kb_members 表 + 成员 API(按 email 添加/列表/移除,仅 owner);权限矩阵 async 化 can_read/can_write/can_manage;list_visible_kbs 含成员库;WebUI 建库三态可见性、共享库 👥 徽标与成员管理弹窗、挂载弹窗图标;迁移 e5a8b1c3d726 | T12.15 | P1 |

### 实施顺序建议

```
T12.1 → T12.2 → T12.3 ─┬─> T12.8 ─┐
              └> T12.4 ─┼─> T12.5 ─┤
                        └─> T12.6 ─┴─> T12.7 → T12.14
T12.3 → T12.9 → T12.11;T12.3 → T12.10
P1:T12.12 / T12.13 在 P0 验收后(已于 M12 P0 验收后完成)
```

### 关键落点备忘

1. **权限红线**(设计 008 §3.3):`kb_ids` 请求参数永不作为授权来源,仅与 allowed 求交集——T12.7 单测必须覆盖「传入未授权 id 返回空+提示」与「跨用户 private 直接拒绝」;
2. **枚举迁移**(ADR 0005):Postgres `ALTER TYPE ... ADD VALUE` 不可回滚,迁移前确认值集一次到位;
3. **embedding 维度**与模型绑定:`skill_tools.schema.embedding_model` 记录,模型变更 = 发布新 kb 版本 + 重跑 pipeline(设计 008 §10 风险 1);
4. **prompt 注入缓解**(设计 008 §9):chunk 包裹声明在 T12.7 落地,文案集中为一处常量便于评审。
