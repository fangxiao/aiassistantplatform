# 技术设计 · 注册表热度与一键引用(020 · 对应需求 015)

- 文档版本:v0.1(20261006,与需求 015 同轮)
- 关联:002-skill-tool-model(注册表)、019(loop 执行包装层埋点同点位)

## 1. 数据模型

`skill_tools` 增 `use_count int not null default 0`(迁移);主键含 version,计数落
具体版本行。存量不回填(从 0 起算,需求 A1)。

## 2. 计数埋点

与 M25 交付物登记同点位:loop `execute()` 包装层,`_execute_inner` 返回后:

```sql
UPDATE skill_tools SET use_count = use_count + 1 WHERE id = :id AND version = :ver
```

- 资源行已由 `resolve()` 加载(id/version 在快照 rid 上,需一并快照 version)
- try/except 静默——计数失败不影响执行(与 artifacts 登记同等自愈语义)
- 同轮次同资源多次调用各计一次(真实使用量口径)

## 3. 透出链路

- `core/registry/capabilities.py get_capabilities_manifest()`:builtin 条目为静态
  构造——**改为注入 DB 计数**(新辅助:批量 `SELECT id, version, use_count` 后按
  id 取最新版本拼入;保持纯函数形态,由调用方传入计数表,离线 CLI 回退 0)
- `/api/registry/*` 列表:响应模型加 use_count;新增 `sort=usage` query 参数
  (`use_count desc, name asc`),默认行为不变(不传参完全兼容)
- `/api/specs/capabilities`:走 manifest 注入,web 与 CLI 自动获得

## 4. 前端(开发者中心 registry tab)

- 能力卡片:右上角热度徽标(`🔥 {n} 次`,0 → `NEW`);「复制引用」按钮
  `navigator.clipboard.writeText("{id}@^{major}.0")`(caret 取当前主版本,
  与 plugin.yaml depends_on 语法一致),2s 「已复制 ✓」反馈
- 列表默认排序切到热度(desc),保留现有 kind 过滤与客户端搜索

## 5. CLI

`cmd_registry` 表格加「使用」列(manifest 条目已有 use_count,纯渲染改动);
远程不可达的离线模式显示 `—`。

## 6. 测试要点

- 埋点:执行成功 +1 / 失败不计 / 计数异常不影响执行
- manifest 注入:有 DB 计数时透出、离线回退 0
- registry API:use_count 字段、sort=usage 排序、不传参兼容
- web vitest:徽标渲染(0/N)、复制按钮剪贴板调用
- E2E 冒烟:真实调一次 tool:pdf_parse → registry 排序与计数 +1

## 7. 落地记录(2026-10-06)

- 迁移 `f5b8d2e7c4a9`;全量 pytest 416 绿(新增 5),web tsc+vitest 绿
- 与设计的偏差:web「复制引用」按钮在既有实现中已存在(dependency_example 一键复制),
  本期未重复实现,仅补热度徽标与默认热度排序;CLI 以 `[🔥 N 次]` 行内标记替代独立列
- 实现细节:自增抽为 `registry/service.bump_use_count`(静默自愈);manifest 保持纯函数
  (usage 由调用方注入,离线 CLI 回退 0);specs 端点改走 get_session 依赖——原直连
  SessionLocal 会绕过测试依赖覆盖打到生产库(测试隔离修复)
- E2E 冒烟(live):真实 run_agent 调 tool:pdf_parse(工具执行并返回)→
  use_count 0→1;`/api/registry/tools?sort=usage` pdf_parse 居首;web/developer 200
