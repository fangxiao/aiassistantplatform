# 需求文档索引

> 平台所有 PRD 的入口。新增 / 修改需求文档时,**同步更新本索引**。

## 文档地图

| # | 文件 | 主题 | 状态 | 对应设计 |
|---|------|------|------|----------|
| 001 | [001-product-requirements.md](./001-product-requirements.md) | 平台总需求(主 PRD) | v1.2 已定稿 | 001-006 全套 |
| 002 | [002-skill-tool-sharing.md](./002-skill-tool-sharing.md) | skill/tool 共享机制(增量) | v1.0 定稿 | [002-skill-tool-model.md](../design/002-skill-tool-model.md) |
| 003 | [003-message-rendering.md](./003-message-rendering.md) | 消息展示扩展 / 21 种 renderer(增量) | v1.0 定稿 | [003-ui-components.md](../design/003-ui-components.md) |
| 004 | [004-remote-dev.md](./004-remote-dev.md) | 远程开发与调试(增量) | v0.1 已实现 | [007-remote-dev.md](../design/007-remote-dev.md) |
| 005 | [005-knowledge-base.md](./005-knowledge-base.md) | 知识库(个人库 + 公共库,增量) | v0.1 草稿待评审 | 008(待产出) |
| 011 | [011-harness-robustness.md](./011-harness-robustness.md) | Agent Harness 加固(断线恢复/并发重构/上下文管理/错误体系) | v0.1 已确认 | [016-harness-robustness.md](../design/016-harness-robustness.md) |
| 012 | [012-feishu-channel.md](./012-feishu-channel.md) | 飞书通道(单聊文本桥接) | v0.1 已实现 | [017-feishu-channel.md](../design/017-feishu-channel.md) |
| 013 | [013-auth-hardening.md](./013-auth-hardening.md) | 认证与账号体系加固(P1 联登/邀请码/PAT;P2 双令牌/飞书扫码/邮箱验证) | v0.3 P1/P2 已交付 | [018-auth-hardening.md](../design/018-auth-hardening.md) |
| 014 | [014-task-deliverables.md](./014-task-deliverables.md) | 任务面板与交付物(工作台任务视角) | v0.1 已交付 | [019-task-deliverables.md](../design/019-task-deliverables.md) |
| 015 | [015-registry-usage.md](./015-registry-usage.md) | 注册表运营面:热度与一键引用 | v0.1 已交付 | [020-registry-usage.md](../design/020-registry-usage.md) |
| 016 | [016-org-context-pack.md](./016-org-context-pack.md) | 组织上下文包(对标千问企业上下文) | v0.1 已交付 | [021-org-context-pack.md](../design/021-org-context-pack.md) |
| 017 | [017-task-entity.md](./017-task-entity.md) | 任务实体化(M25 聚合的实体演进) | v0.1 已交付 | [022-task-entity.md](../design/022-task-entity.md) |

## 阅读路径

**首次了解平台**:
1. [../vision.md](../vision.md) — 产品愿景
2. [001-product-requirements.md](./001-product-requirements.md) — 平台总需求
3. (按需)002 / 003 — 增量需求的细化

**实现者**:
1. 001 — 了解全貌
2. 任务拆解:[../tasks/001-task-breakdown.md](../tasks/001-task-breakdown.md)
3. 涉及的增量需求 002 / 003

**评审 / 贡献需求**:
1. 顶部"状态"列查看哪些待评审
2. 按文档号顺序读;增量文档优先看 §"与 001 的关系"再读细节

## 增量文档与主需求的关系

| 增量 | 细化 001 的哪些条款 | 状态 |
|------|---------------------|------|
| 002 | §F7 skill/tool 复用与显式调用(替代 §F7.5 / F7.6"待设计"标记) | 已定稿 |
| 003 | §F3 对话与富交互 UI(扩展 21 种 renderer;替代 §8.2"组件协议细节"留待设计) | 已定稿 |
| 005 | §1.2 可复用生态的延伸——知识库作为第三类注册表资源;§F3 对话的知识增强 | 草稿待评审 |

## 维护规则

- **新增增量需求**:在本 README 表格加一行,在"增量文档与主需求的关系"中标注细化的 001 条款
- **状态变化**:草稿 → 待评审 → 已定稿,同步本 README
- **001 不动原则**:001 是定稿文档(v1.2),**不在 001 内部加增量引用**;增量文档自己反向引用 001
- **编号规则**:需求文档独立从 001 起编号;与设计(`../design/`)和任务(`../tasks/`)的编号互不冲突
- **增量文档自身要求**:文件头必须有"对应主需求"、"对应设计"、"变更记录"三段;§"决策状态"必须有"与 001 的关系"小节
