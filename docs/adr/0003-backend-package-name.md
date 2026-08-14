# 0003 · 后端包名:agentplatform(弃用 platform)

- 日期:2026-08-13
- 状态:已接受
- 关联:001 §2.1、006 §5、需求 003、ADR 0002

## 背景

设计 001 §2.1 将后端包命名为 `platform/`(模块 `platform.api` / `platform.sdk` 等)。M0 实现时发现硬冲突:

- Python stdlib 自带同名 `platform` 模块,且被广泛库内部依赖(如 SQLAlchemy `util/compat.py` 的 `platform.python_implementation()`)
- 包一旦安装(editable/site-packages),`import platform` 在**任意进程**里都解析到我们的包 → `import sqlalchemy` 直接崩溃(`AttributeError: module 'platform' has no attribute 'python_implementation'`),已实测复现
- 没有干净方式保留该导入名:只要我们的包可达,SQAlchemy 等库就拿错模块

## 决策

后端包名定为 **`agentplatform`**:

- 目录 `platform/` → `agentplatform/`;内部导入 `from agentplatform.api import ...`
- 插件 SDK 导入 `from agentplatform.sdk import Skill`(006 §5 同步)
- CLI 命令名不变(`agentplatform init/validate/deploy ...`);包名与仓库名/CLI 名统一

## 后果

- 消除 stdlib `platform` 冲突,SQLAlchemy 等库正常导入
- 需同步文档:001 §2.1、006 §5、需求 003、ADR 0002、任务拆解、CLAUDE.md(已同步)
- pytest 用 `--import-mode=importlib`(pyproject 配置),防御性规避与 stdlib 同名的收集问题

## 替代方案

| 方案 | 问题 |
|------|------|
| `platform_core` | 保留前缀但加后缀;与仓库/CLI 名不一致,`platform_core.sdk` 语义略怪 |
| `core` | 过于通用,与内部 `core/` 子模块(agent/llm/...)混淆 |
