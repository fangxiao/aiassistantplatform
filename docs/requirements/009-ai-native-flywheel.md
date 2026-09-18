# 需求文档 · AI-Native 开发飞轮(M16)

- 文档版本:v0.1(草案,待评审)
- 日期:2026-09-18
- 流程阶段:阶段 1 · 需求
- 背景:平台最深的护城河是**可编程插件生态**+**AI-native 开发闭环**(init→AI 开发→
  validate/test→deploy)。本里程碑不新增平台功能,而是把这个闭环的体验推到极致——
  让"一个想法变成合格插件"的路径从"能用"变成"半小时飞轮",这是生态增速的核心杠杆。

---

## 1. 问题陈述(以 AI(Claude Code)为第一用户的走查)

当前开发者用 Claude Code 开发插件的路径与堵点:

| 步骤 | 现状 | 堵点 |
|---|---|---|
| 装环境 | curl install.sh 一键 ✅ | — |
| 脚手架 | init 生成 demo 骨架 | **结构要从零想**:demo 与真实场景(周报/文档问答)差距大,AI 要自己搭目录与 schema |
| 能力发现 | `agentplatform registry` 人看友好 | **AI 不知道平台有什么可复用**:capabilities/注册表数据在 API 里,AGENTS.md 是静态文本,AI 开发时不会主动查 → 重复造轮子、依赖写错 |
| 开发 | AGENTS.md 规范 | 规范未覆盖新能力(memory/web_search/kb 挂载/定时任务),AI 用旧姿势 |
| 自愈 | validate/test 结构化 JSON ✅ | 高频错误(缺版本约束/id 前缀/schema 缺 required)提示可再"可操作"——直接给修法 |
| 部署 | deploy 准入 ✅ | — |

## 2. 目标

1. **模板化冷启动**:`agentplatform init <name> --template <场景>` 生成的骨架
   **validate 与 test 直接通过**,AI 只填领域逻辑;
2. **能力上下文一键注入**:`agentplatform context` 输出当前平台真实可复用资源
   (工具/技能/kb 及版本)+ 关键规范摘要,可直接粘进 AI 会话;
3. **规范教科书化**:AGENTS.md 升级,覆盖全部新能力、模板用法与高频错误对照;
4. 全链路实测:用 Claude Code 在模板上从 init 到 deploy ≤ 30 分钟、零人工修错。

## 3. 用户故事

- **U1 模板列表与选择**:`agentplatform templates` 列出可用模板(名称/场景/含什么);
  `init <name> --template weekly-report` 生成该场景骨架。
- **U2 模板内容标准**:每个模板含完整可运行的 plugin.yaml + ≥1 个 skill/tool + 
  test 用例(自带且通过)+ README(说明改哪里);依赖真实存在的平台资源。
- **U3 能力上下文**:`agentplatform context`(可 --target)输出 markdown:
  可用 tools/skills(含版本与一句话说明)、可依赖的公共 kb、22 控件清单摘要、
  规范要点(命名空间/依赖语法/部署准入)——供粘贴进 AI 会话。
- **U4 validate 修复建议**:高频错误附 hint 字段(错误码→修法示例),如
  `kb: 依赖缺少版本约束 → 改为 kb:xxx@^1.0`。
- **U5 规范模板 v0.4**:AGENTS.md 增补:memory/web_search 工具、kb 依赖与挂载、
  定时任务能力说明、模板使用说明、"开发前先跑 agentplatform context"的指令。
- **U6 模板随平台升级**:模板与规范经 `agentplatform update` 同步(存平台端,
  CLI 拉取),保证"本地骨架 = 平台当前能力"。

## 4. 验收标准

1. `agentplatform templates` 正常列出;每个模板 init 后 **validate 零错误、test 全过**;
2. context 输出与注册表实际资源一致(含版本),人类与 AI 均可读;
3. 端到端:用 Claude Code 基于模板开发一个新插件(改动领域逻辑)→ deploy 成功,
   全程无人工修 validate 错误,耗时 ≤ 30 分钟;
4. 高频错误均带 hint;模板/规范经 update 可同步更新。

## 5. 非功能约束

- 模板存**平台端**(specs API 下发),CLI 按 target 拉取——"本地骨架 = 平台能力"持续成立;
  无网时回退内置最小模板;
- 模板质量即生态门面:每个模板必须自带通过的 test 用例(准入自动化);
- 不改变现有 init 的向后兼容(无 --template 时保持 demo 骨架)。

## 6. 首批模板(质量优先于数量)

| 模板 | 场景 | 依赖演示 |
|---|---|---|
| starter | 现有 demo(保持) | pdf_parse/summarize |
| weekly-report | 工作周报生成 | structured_output + kb |
| doc-summarizer | 文档摘要问答 | kb_search |
| web-digest | 网页内容日报 | html_cleaner + web_search |

## 7. 范围外(后续)

- 用户上传/分享自定义模板(模板市场);插件一键导出为模板;
- 在线插件 IDE;计费与商业化。
