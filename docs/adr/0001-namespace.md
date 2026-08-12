# 0001 · 命名空间规则

- 状态:**Accepted**
- 日期:2026-08-12
- 适用:[002 §3](../requirements/002-skill-tool-sharing.md) / [003 §3](../requirements/003-message-rendering.md) 引用本 ADR
- 决策范围:renderer、skill、tool 三类资源的全局唯一标识规则

## 背景

平台有三种需要在系统内全局唯一标识的资源:

1. **renderer**:消息块的 UI 渲染器,运行在 WebUI 前端
2. **skill**:平台级能力单元,在主 agent 或子 agent 中被调用
3. **tool**:平台级函数接口,被 LLM 通过 function-calling 显式调用

它们特性不同,需要差异化命名空间:

- renderer 跟 UI 强耦合,需要避免跨插件命名冲突(前端代码在 WebUI 进程内运行,所有插件共享同一个 namespace)
- skill / tool 是平台级资源,**独立于插件存在**——`shared` 资源可能在原贡献者插件卸载后仍被引用
- skill / tool 需要在 OpenAI function-calling 的 `tools` 参数里出现,schema 兼容性优先

## 决策

| 资源 | 命名格式 | 示例 | 前缀来源 |
|------|----------|------|----------|
| **renderer** | `<name>` 或 `<plugin_id>.<name>` | `markdown` / `weather.card` | 平台内置无前缀,插件带 `plugin_id` |
| **skill id** | `skill:<name>` | `skill:summarize` | 类型前缀,不带 `plugin_id` |
| **tool id** | `tool:<name>` | `tool:pdf_parse` | 类型前缀,不带 `plugin_id` |

- **renderer**:`plugin_id` 由平台分配 / 开发者声明,格式 `^[a-z0-9_-]+$`;`name` 同上;完整 ID 即注册 key
- **skill / tool**:`name` 段需全局唯一(不强制 plugin 命名空间);`skill:` / `tool:` 是类型前缀,运行时用于 function-calling 区分 kind

## 理由

### 为什么 renderer 强制带 plugin_id 前缀

- renderer 在 WebUI 进程内运行,所有插件共享同一个前端 namespace;**不强制前缀会导致插件 A 注册 `card` 跟平台内置 `card` 冲突**
- 平台内置 renderer 是"保留名"(`markdown` / `code` / `image` 等),插件不允许注册同名
- 命名空间在 003 §F-MR-8.5 锁定

### 为什么 skill / tool 不带 plugin_id 前缀

- skill / tool 是平台级资源,独立于插件存在——`shared` 资源可能在原贡献插件卸载后仍被引用(对齐 002 §F-ST-7.5)
- 带 `plugin_id` 前缀会**人为绑定**资源和插件,违反"资源脱离插件"原则
- 类型前缀 `skill:` / `tool:` 满足"区分 kind"需求,且天然支持跨插件共享

### 为什么不统一规则

- renderer 和 skill / tool 的**运行环境不同**:renderer 跑在前端(WebUI 进程),skill / tool 跑在后端(平台进程)
- 命名空间规则应贴近**实际冲突域**:前端需要 plugin 隔离,后端按 kind 区分
- 强行统一会带来不必要的约束(如 shared skill 必须带原 plugin 前缀,导致资源"认祖归宗"反生态)

## 影响

- 002 §3 / 003 §3 引用本 ADR
- 插件作者需注意:
  - 自有 renderer **必须**带 `plugin_id` 前缀
  - 自有 skill / tool 只需全局唯一 id(不需要 `plugin_id` 前缀)
- 平台不允许 `markdown` / `code` / `image` 等保留名作为插件 renderer 注册
- 后续:跨插件 renderer 复用(留 v1.4 评估)需考虑命名空间扩展机制

## 替代方案

### 方案 A:全部带 plugin_id 前缀
- ✅ 规则统一
- ❌ shared skill 必须带原 plugin 前缀,资源绑定插件,违反"独立于插件"原则(002 §F-ST-7.5)

### 方案 B:全部不带 plugin_id 前缀
- ✅ 规则统一
- ❌ renderer 在前端共享 namespace,跨插件命名冲突风险;需要额外保留名机制

### 方案 C(采用):按"实际冲突域"差异化
- ✅ renderer 在前端,带 `plugin_id` 强制隔离
- ✅ skill / tool 在后端,按 kind 前缀(全局唯一即可)
- ❌ 两套规则,新人需学习

## 相关决策

- 002 §F-ST-3.5 插件自有语义边界(独立实现,不能覆盖/包装)
- 003 §F-MR-8.5 renderer 命名空间
- 003 §F-MR-9 UI 扩展性边界(只支持 renderer 挂件)
