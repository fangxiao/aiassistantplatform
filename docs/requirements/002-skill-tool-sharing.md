# agentplatform skill/tool 共享需求文档(PRD)

- 文档版本:v1.0
- 日期:2026-08-12
- 流程阶段:阶段 1 · 需求(增量)
- 对应主需求:[001-product-requirements.md](./001-product-requirements.md) §F7
- 对应设计:[../design/002-skill-tool-model.md](../design/002-skill-tool-model.md)(已定稿)
- 关系:001 §F7 的需求层细化;001 v1.2 不动,本文档作为 002 增量

## 变更记录
- v1.0(2026-08-12):初稿。把设计 002-skill-tool-model.md 已有方案落到需求层(用户故事 + 功能 + 验收 + 非功能);不重写设计 002,只补需求闭环。
- v1.0(2026-08-12 同日补):新增 §F-ST-3.5 插件自有的语义与边界(独立实现 / 不覆盖 / 不依赖插件);ADR 0001 命名空间规则配套。
- v1.0(2026-08-12 评审通过):定稿,无进一步修改。

---

## 1. 背景与目标

### 1.1 背景
001 §F7 把"skill/tool 复用与显式调用"立为平台**第一特色**,但仅到概念层:F7.5(skill 组合性)和 F7.6(来源与权限)都明确"待设计"。设计 002-skill-tool-model.md(2026-08-11 定稿)已把机制设计完整,但需求层未同步闭环——缺用户故事、验收标准、非功能约束,也无法作为"实现合同"对外承诺。

本文档把设计 002 的方案"翻译"为需求层表达,与设计 1:1 对应,补齐 001 F7 的需求细节。

### 1.2 目标
- skill/tool 提升为**平台级资源**,登记在统一注册表,独立于插件存在
- 插件通过清单声明依赖,部署时自动校验版本兼容
- 跨插件共享:平台内置 / 开发者贡献的公共资源,任意插件 `depends_on` 即可复用
- 运行时通过 OpenAI function-calling **显式调用**(模型 C),非黑盒文本
- MVP 默认跨插件可复用,降低生态门槛

### 1.3 非目标(MVP 不做)
- 不做细粒度授权(按插件/开发者圈选可见范围)
- 不做 marketplace / 审核 / 评分流程
- 不做 skill 调用 skill 的组合性
- 不做跨语言 skill/tool(仅 Python)
- 不做跨实例注册表同步(单机部署即可)

---

## 2. 用户角色

沿用 001 §2。本节列出与本文档最相关的角色关切:

| 角色 | 核心关切 |
|------|----------|
| 开发者(资源贡献者) | 把自写 skill/tool 共享到公共池,被其他插件引用 |
| 开发者(资源消费者) | `depends_on` 平台内置 / 他人共享的 skill/tool,部署时自动校验 |
| 平台管理员(Operator) | 维护 `builtin` 列表;管理 `shared` 资源(下架/弃用) |

---

## 3. 核心概念

| 概念 | 定义 |
|------|------|
| **Registry(注册表)** | 平台维护的 skill/tool 资源池;元信息存 PostgreSQL,实现代码进程内加载 |
| **Resource ID** | 全局唯一,前缀区分 kind:`tool:pdf_parse` / `skill:summarize` |
| **Source(来源)** | 三类:`builtin`(平台内置) / `shared`(开发者贡献,公共) / `private`(插件私有) |
| **依赖声明(depends_on)** | 插件清单 `plugin.yaml` 声明用到的资源,用 semver 约束 |
| **显式调用** | LLM 通过 OpenAI function-calling 协议结构化发起调用,平台执行后回填 |
| **简单 skill** | prompt 模板 + 参数,一次 LLM 调用完成 |
| **复杂 skill** | 子 agent,多轮完成(**MVP 不支持**) |

### 3.1 资源元信息(摘自设计 002 §3.2)
```yaml
id: tool:pdf_parse
name: pdf_parse
version: 1.2.0
kind: tool                # tool | skill
source: builtin | shared | private
owner: platform | <developer>
description: 解析 PDF 为文本
schema:                   # OpenAI function 兼容
  parameters: { type: object, ... }
  returns: { type: string }
```

### 3.2 插件清单(摘自设计 002 §4)
```yaml
name: prd-review-assistant
version: 0.1.0
model: glm-5.2
depends_on:               # 复用公共资源
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0
skills:                   # 自有 skill
  - id: skill:prd_review
    file: ./skills/prd_review.py
tools: []
```

---

## 4. 功能需求

### F-ST-1 注册表
- F-ST-1.1 平台维护统一注册表,所有 skill/tool 须登记方可被调用
- F-ST-1.2 元信息存 PostgreSQL,实现代码进程内加载(MVP)
- F-ST-1.3 提供按 id / name / version / source / owner 的查询接口(平台内部 API)
- F-ST-1.4 注册表变更(登记 / 更新 / 弃用 / 删除)记审计日志

### F-ST-2 资源元信息
- F-ST-2.1 每个资源有:全局唯一 id、name、version(semver)、kind、source、owner、description、input/output schema
- F-ST-2.2 schema 必须兼容 OpenAI function 协议(`parameters` / `returns`),运行时直接映射
- F-ST-2.3 元信息变更 = 发布新版本,已部署引用方继续用旧版本直到下次部署(对齐 001 §F1.7 插件生命周期)

### F-ST-3 来源分类
- F-ST-3.1 `builtin`:平台内置,owner = `platform`;管理员通过运维手段置入
- F-ST-3.2 `shared`:开发者贡献到公共池,任意插件可 `depends_on`
- F-ST-3.3 `private`:插件私有,仅该插件可引用;随插件部署登记,随插件卸载移除
- F-ST-3.4 同一资源可在插件清单中显式标记 `shared` 提升为公共(MVP 走自动登记,不审核)

### F-ST-3.5 插件自有的语义与边界

> 回答"插件能不能定制 / 包装 / 覆盖 skill/tool"的问题。MVP 锁定**独立实现,不能覆盖/包装**。

- F-ST-3.5.1 插件"自有 skill/tool" = 插件作者**独立实现**的 skill/tool,登记为 `private`(可选标 `shared` 提升为公共)。**不**复用、**不**覆盖、**不**包装平台 `builtin` 或他人 `shared` 资源
- F-ST-3.5.2 **同 id 禁止覆盖**:插件部署时,若清单里出现与注册表已有 `builtin` / `shared` 资源同 id 的自有 skill/tool,部署失败(避免静默覆盖)
- F-ST-3.5.3 **插件不能"包装"别人的 skill**:注册表层**不记录** skill 间的依赖关系——一个 skill 不能"基于"另一个 skill 在注册表里声明(避免组合性)
- F-ST-3.5.4 **代码层组合允许**:插件内部 skill 实现**可以**调用 shared skill/tool(就是普通函数调用),但这种"包装"不进注册表,对其他插件不可见
- F-ST-3.5.5 **插件不能直接依赖另一个插件**:`depends_on` 只接 skill/tool id,不接 plugin id;若 B 插件想用 A 插件的能力,需 A 把对应 skill 标 `shared` 后,B 才能 `depends_on`

### F-ST-4 依赖声明
- F-ST-4.1 插件清单 `plugin.yaml` 用 `depends_on` 数组声明公共依赖
- F-ST-4.2 依赖项格式:`<id>@<version_constraint>`,支持 `^` / `~` / 精确版本
- F-ST-4.3 自有 skill 列 `skills` 段,自有 tool 列 `tools` 段,自动登记为 `private`
- F-ST-4.4 依赖可跨插件共享(A 插件贡献 `tool:foo` 为 shared,B 插件可 `depends_on: tool:foo@^1`)

### F-ST-5 部署校验
- F-ST-5.1 部署插件时,平台校验 `depends_on` 每个 id 在注册表中存在
- F-ST-5.2 解析 semver 约束,匹配失败返回结构化错误(列出冲突项 + 候选版本)
- F-ST-5.3 校验失败 = 部署拒绝,插件不进入已部署态,自有资源不登记
- F-ST-5.4 校验通过 = 插件进入"已部署"态,自有 skill/tool 登记注册表

### F-ST-6 运行时调用(显式 / 模型 C)
- F-ST-6.1 agent 调度 LLM 时,把插件依赖的 skill/tool 映射为 OpenAI function-calling 的 `tools` 参数
- F-ST-6.2 LLM 通过 `tool_calls` 发起调用,平台执行对应 skill/tool
- F-ST-6.3 执行结果以 `tool` 角色 message 回填到 messages,继续推理
- F-ST-6.4 tool 执行:同步函数调用,直接返回结果
- F-ST-6.5 skill 执行:简单 skill = prompt 模板 + 参数,一次 LLM 调用完成
- F-ST-6.6 权限语义(MVP):平台内 `builtin` / `shared` 资源默认可被任意已部署插件复用,**不做细粒度授权**
- F-ST-6.7 LLM 端点失败时,工具调用错误回填给 LLM,继续推理(不中断会话);MVP 不做跨端点自动降级(对齐 001 §F6.4)

### F-ST-7 生命周期
- F-ST-7.1 资源登记:插件部署时自动登记私有资源;`builtin` 由管理员预置;`shared` 由开发者主动标记或单独发布
- F-ST-7.2 版本演进:资源变更 = 发布新版本(semver);旧版本默认保留,引用方按约束解析
- F-ST-7.3 弃用:owner 标记 `deprecated`;引用方部署时告警(非阻塞,允许继续)
- F-ST-7.4 删除:owner 发起;前置检查"无活跃引用"或选择"强制删除"(引用方下次部署失败)
- F-ST-7.5 插件卸载:私有资源同步移除注册表;`shared` 资源**保留**(已脱离插件独立存在)
- F-ST-7.6 插件禁用期间,其私有资源仍登记但禁止新会话调用(对齐 001 §F1.7)

---

## 5. 非功能需求

- **性能**:注册表查询 P95 < 10ms(单实例内,PostgreSQL 命中);依赖解析 P95 < 100ms(对一份 10 条 depends_on 的清单)
- **可扩展**:注册表存储可从 PostgreSQL 单库演进到分片 + 缓存(Redis);实现代码加载可从进程内演进到进程/容器隔离(对齐 001 §5)
- **可观测**:每次资源调用结构化日志 `{resource_id, version, session_id, plugin_id, latency_ms, status}`;注册表变更记审计日志(谁、何时、改了什么)
- **可测试**:每个 skill/tool 自带单元测试 + schema 契约测试;平台提供 mock skill 用于插件独立测试
- **版本兼容**:schema 演进走 semver——主版本 = breaking(引用方需升级),次版本 = 向后兼容新增,补丁 = bugfix
- **安全**(对齐 001 §5 MVP 假设):可信开发者 / 内部部署;资源 id 不可伪造(命名空间 + 部署期校验);不做对抗性隔离

---

## 6. 验收标准

### 6.1 共享功能
- [ ] 平台内置 ≥ 3 个 skill/tool(如 `tool:pdf_parse` / `skill:summarize` / `skill:structured_output`)
- [ ] 开发者 A 部署一个插件,把自有 skill 标记为 `shared`
- [ ] 开发者 B 在另一插件 `depends_on` 引用 A 的 shared skill,部署校验通过,运行时可调用
- [ ] 删除 A 的 shared skill 时,如有活跃引用 → 告警并要求确认 / 拒绝

### 6.2 依赖校验
- [ ] 依赖 id 在注册表中不存在 → 部署失败,返回结构化错误(指明缺失的 id)
- [ ] 版本约束不满足 → 部署失败,返回候选版本列表
- [ ] 校验通过 → 插件进入已部署,自有资源登记成功

### 6.3 显式调用
- [ ] LLM 返回 `tool_calls` → 平台正确执行对应 skill/tool
- [ ] 执行结果以 `tool` 角色 message 回填,对话继续
- [ ] 简单 skill(prompt 模板)执行成功,参数按 schema 注入
- [ ] 复杂 skill / 嵌套调用(MVP 不支持)→ 报错并提示"MVP 不支持"

### 6.4 生命周期
- [ ] 资源发布新版本,引用方按 semver 自动解析匹配版本
- [ ] 资源标记 `deprecated`,引用方部署时收到告警
- [ ] 插件卸载,私有资源从注册表消失,共享资源保留
- [ ] 插件禁用期间,新会话拒绝调用其私有资源(在 001 §F1.7 范围内)

### 6.5 安全基线
- [ ] 资源 id 命名空间隔离(插件无法伪造 `tool:foo` 指向未注册实现)
- [ ] 部署 CLI 调用部署接口需 API token 鉴权(对齐 001 §F5.4)

---

## 7. 决策状态

### 7.1 已确认(本 002 锁定)
- ✅ 来源分类:三类(`builtin` / `shared` / `private`),MVP 默认跨插件可复用
- ✅ 注册表存储:元信息 PostgreSQL + 实现进程内加载
- ✅ 依赖校验:部署期强制,semver 约束,失败拒绝部署
- ✅ 显式调用:统一映射 OpenAI function-calling 协议(模型 C)
- ✅ skill 执行模型:MVP 仅支持"简单 skill(prompt 模板 + 参数)"
- ✅ 资源版本:发布新版本演进,旧版本可保留
- ✅ 资源弃用:owner 标记,引用方告警(非阻塞)
- ✅ 复杂 skill(子 agent 形态):MVP 不支持
- ✅ skill 组合性(skill 调用 skill):MVP 不支持 + 注册表预留 `depends_on` 字段
- ✅ 插件自有 skill/tool = **独立实现,不能同 id 覆盖** builtin/shared(部署期校验)
- ✅ 插件不能直接依赖另一个插件,只能通过 shared skill/tool 间接复用
- ✅ 组合性两层语义:**注册表层不支持**(MVP)+ **代码层允许**(不进注册表)

### 7.2 留待设计 / 后续版本
- 共享资源的"可见范围"是否需要按插件/开发者圈选(目前默认全平台)— 留 v1.4 评估
- 资源发布 / 弃用 / 删除的工作流(CLI 命令集 + 管理员界面)— 设计 006-plugin-spec 补
- 跨实例注册表同步(多机部署)— 部署形态扩展,留待后续
- 资源评分 / 使用统计 / 推荐 — 生态化阶段

### 7.3 与 001 的关系
- 001 §F7 全段范围以本文档 + 设计 002 为准
- 001 §F7.5 / F7.6 "待设计" 标记 → 由本文档 + 设计 002 闭环
- 001 §8.2 "skill 组合性 / skill/tool 来源与权限" → 锁定状态,见 §7.1

---

## 8. 实现映射

设计 002-skill-tool-model.md(定稿)与本文档 1:1 对应:

| 需求章节 | 对应设计章节 |
|----------|--------------|
| F-ST-1 注册表 | 设计 002 §3 |
| F-ST-2 元信息 | 设计 002 §3.2 |
| F-ST-3 来源 | 设计 002 §7.1 |
| F-ST-4 依赖声明 | 设计 002 §4 |
| F-ST-5 部署校验 | 设计 002 §4 + §8 |
| F-ST-6 运行时调用 | 设计 002 §5 |
| F-ST-7 生命周期 | 设计 002 §8 |

实现任务见 [../tasks/001-task-breakdown.md](../tasks/001-task-breakdown.md) Phase 2(skill/tool 注册表 / 部署校验 / function-calling 集成)。
