# 013 · AI-Native 开发飞轮设计

- 文档版本:v0.1
- 日期:2026-09-18
- 流程阶段:阶段 2 · 设计
- 对应需求:[009-ai-native-flywheel](../requirements/009-ai-native-flywheel.md)

## 1. 模板机制(平台下发,CLI 消费)

```
agentplatform/cli_templates/(平台包内数据模块)
    TEMPLATES: {id: {name, description, files: {相对路径: 内容}}}
        ▼ GET /api/specs/templates            → [{id, name, description}]
        ▼ GET /api/specs/templates/{id}       → {id, name, description, files{}}
CLI: init <name> --template <id>
    拉取模板 → {plugin_name} 占位符替换 → 写文件 → 跳过 demo 生成
    平台不可达时回退内置 starter(与现有 demo 等价)
```

- 模板文件随 **package.tar.gz** 分发(cli_templates 在 SDK 包内),`agentplatform update`
  即同步——"本地模板 = 平台能力"持续成立;
- 模板准入自动化:每个模板的骨架必须 `validate_project` 零错误、`run_tests` 全过
  (单测覆盖,质量门禁与业务插件同规格);
- `plugin.yaml` 中 name/display_name 以 `{plugin_name}` 占位,init 时替换;测试用例
  为结构校验级(test_cases 现状),零 LLM 依赖即可通过。

## 2. context 命令

`agentplatform context [--target URL]` → 输出 markdown(可直接粘进 AI 会话):

- 可复用 tools/skills:调 `GET /api/specs/capabilities`(无鉴权,含版本与描述);
- 22 控件摘要(名称+用途);
- 规范要点:命名空间、依赖语法(`^`/`~`/`?`)、kb 依赖、部署准入;
- 提示语:"将本段粘贴给 AI 作为开发上下文"。

无网络时:输出本地内置资源的回退版并标注。

## 3. validate 修复建议

错误字符串内嵌修法(不改结构,兼容现有消费方):

```
"kb: 依赖必须带版本约束(如 kb:product_docs@^1.0): kb:foo"
```
已是该风格——本次补齐其余高频错误:依赖格式错误/资源 id 前缀/缺 file/装饰器未找到。

## 4. AGENTS.md v0.4(教科书化)

增补:web_search/memory 工具用法、kb 依赖与助手挂载、定时任务能力、模板与
context 使用说明、test 用例写法示例、高频错误对照。

## 5. 任务

| ID | 内容 |
|----|------|
| T16.1 | cli_templates 包(starter + weekly-report + doc-summarizer + web-digest)+ specs templates API |
| T16.2 | CLI:init --template / templates / context 命令 |
| T16.3 | validate hint 补齐 + AGENTS.md v0.4 |
| T16.4 | 测试(模板准入自动化/context 输出/端点)+ 真实 Claude Code 走查 + 文档 |
