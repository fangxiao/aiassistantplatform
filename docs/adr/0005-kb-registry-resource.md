# ADR 0005: 知识库作为注册表资源(kind 扩展),而非独立依赖体系

- 状态:已接受
- 日期:2026-09-05
- 关联:需求 005、设计 008 §2/§3.2/§4.1

## 背景

公共知识库需要支持插件 `depends_on: ["kb:product_docs@^1.0"]` 静态依赖与 SemVer 解析。两种做法:

- A. 在现有 `skill_tools` 注册表上扩展 `kind` 枚举增加 `kb`,复用既有 `(id, version)` 复合主键、`check_dependencies` 解析链路;
- B. 知识库独立建表(knowledge_bases),为 `kb:` 依赖单独实现一套校验与版本解析逻辑。

## 决策

采用 **A**:扩展 `skill_tools.kind` 增加 `kb`;`knowledge_bases` 表承载内容与权限,注册表行仅承担依赖解析职责(`impl_path` 为空,`schema` 记录 embedding_model/chunk_size 等元信息)。

## 理由

1. `kb:<slug>` 与 `tool:pdf_parse` 完全同构(有 id、SemVer、来源、owner),心智与「知识库即资源」的产品定位一致;
2. `core/plugin/loader.py` 的 `check_dependencies` 与 `chat/service.py` 的 `split_dependency` 均**零改动**通过——`kb:` 依赖的校验、解析、冲突消解自动复用 002 §8 全部语义;
3. 避免两套版本解析逻辑并存(方案 B 需要在 validate/loader/chat 三处各加 kb 分支);
4. `agentplatform registry` 列表自然出现 kb 行,CLI 零开发(需求 F4.1)。

## 后果

- 公共库发布/下架需同时写 knowledge_bases 与 skill_tools(发布事务内完成,008 §7 publish 接口);
- `SkillToolKind` 枚举扩展需 Postgres enum 迁移(ALTER TYPE ADD VALUE);
- kb 注册表行没有可执行实现,消费方(chat 侧)需按 kind 判别处理——与 skill(参数化执行)不同于 tool(直接执行)的现有判别模式一致。
