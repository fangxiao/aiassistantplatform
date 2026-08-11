# 002 · skill/tool 模型设计【第一特色核心】

- 文档版本:v1.0(定稿)
- 日期:2026-08-11
- 流程阶段:阶段 2 · 设计
- 对应需求:F7(skill/tool 复用与显式调用)

---

## 1. 设计目标

把 skill/tool 从"插件内部实现"提升为"平台级可复用资源",使插件能声明依赖并显式调用,实现网络效应(资源越多,新插件越快)。对应需求 F7、vision 特色一。

## 2. skill 与 tool 的定义

| | tool | skill |
|---|------|-------|
| 本质 | 确定性的编程接口(函数) | 能力/知识单元(行为定义,通常含 prompt 模板) |
| 执行 | 直接调用代码,返回结果 | 参数化执行:用输入参数激活其行为,可能作为子 agent 运行 |
| 例 | `pdf_parse(file) -> text` | `summarize(text, style) -> summary` |
| 复用粒度 | 单一功能 | 一类能力 |

两者都是**平台级资源**,有元信息、版本、来源,登记在注册表中。

## 3. skill/tool 注册表(Registry)

### 3.1 职责
- 存储所有可用的 skill/tool(平台内置 + 开发者共享 + 插件私有)
- 提供按 id/名称/版本查询
- 依赖解析:插件部署时校验其声明的依赖是否存在、版本是否兼容

### 3.2 资源元信息
```yaml
id: tool:pdf_parse           # 全局唯一,前缀区分 skill/tool
name: pdf_parse
version: 1.2.0
kind: tool                    # tool | skill
source: builtin | shared | private   # 来源(见 §7)
owner: platform | <developer>
description: 解析 PDF 为文本
schema:                       # OpenAI function 兼容的输入输出 schema
  parameters: { type: object, properties: { file: {...} }, required: [file] }
  returns: { type: string }
```

### 3.3 存储
- 元信息:PostgreSQL(`skill_tool_registry` 表)
- 实现代码:进程内加载(从部署目录加载 Python 模块);后续隔离模式可改为引用远程实现

## 4. 依赖声明(插件清单)

插件在 `plugin.yaml` 声明依赖的公共 skill/tool + 自有的:

```yaml
# plugin.yaml
name: prd-review-assistant
version: 0.1.0
model: glm-5.2
depends_on:                    # 引用公共资源(复用)
  - tool:pdf_parse@^1.0
  - skill:summarize@^1.0
  - skill:structured_output@^1.0
skills:                        # 自有 skill
  - id: skill:prd_review
    file: ./skills/prd_review.py
tools: []                      # 自有 tool(本插件无)
ui_components: [...]           # 富交互组件声明(见 003)
```

部署时:CLI 校验 `depends_on` 在注册表中存在且版本兼容;自有 skill/tool 登记到注册表(标记 `source: private` 或 `shared`)。

## 5. 显式调用协议(模型 C)【核心】

### 5.1 映射到 OpenAI function-calling
agent 调用 LLM 时,把插件依赖的所有 skill/tool **映射为 OpenAI 兼容协议的 `tools` 参数**(function 定义)。LLM 通过 `tool_calls` **显式**发起调用,平台执行后回填。

```
agent 组装请求:
  messages = [系统提示(skill 上下文), 历史, 用户消息]
  tools = [插件依赖的所有 skill/tool 转为 function schema]

LLM 返回:
  tool_calls: [{ name: "tool:pdf_parse", args: {file: "..."} }]

平台执行:
  tool:pdf_parse -> tool 执行器 -> 结果
  (若为 skill) -> skill 执行器(参数化执行/子 agent)-> 结果

回填:
  messages += [tool 角色 message 含结果]
  -> 再推理
```

### 5.2 为什么用 function-calling
- 复用 OpenAI 兼容协议,不发明新协议
- "显式":LLM 结构化输出 tool_call,非黑盒文本
- skill/tool 统一为可调用单元,机制一致
- 主流模型(glm/deepseek/minimax)均支持 function-calling

### 5.3 skill 的执行模型
- **简单 skill**:prompt 模板 + 参数,调用时填充参数作为子任务,可一次 LLM 调用完成(如 `summarize`)
- **复杂 skill**:可作为子 agent,有自己的依赖 skill/tool,多轮完成(MVP 可先支持简单形态,复杂形态后续)
- skill 执行结果以 `tool` 角色 message 回填主 agent

## 6. skill 调用 skill 的组合性(F7.5)

**决策**:MVP **不支持** skill 内部显式调用其他 skill(已列为 7.2 非目标),但注册表与调用协议**预留组合性**:
- skill 元信息可声明 `depends_on`(依赖其他 skill)
- 后续支持时,skill 执行器递归调用,需做环检测与深度限制

**理由**:MVP 先把"agent 显式调用 skill/tool"跑通;组合性引入递归/环/上下文嵌套,复杂度高,放到第二阶段。

## 7. 来源与权限(F7.6)

### 7.1 来源分类
| 来源 | 说明 |
|------|------|
| `builtin` | 平台内置基础资源(PDF 解析、摘要、结构化输出等) |
| `shared` | 开发者贡献到公共池,其他插件可引用 |
| `private` | 插件自带,仅该插件可用 |

### 7.2 权限
- MVP:**平台内默认可复用**(`builtin`/`shared` 任意插件可引用),不做细粒度授权
- 后续:`shared` 资源可加审核/可见范围;`private` 仅_owner_

**理由**:MVP 优先促生态(降低复用门槛);权限/审核在规模化后引入。

## 8. 生命周期

| 阶段 | 行为 |
|------|------|
| 注册 | 插件部署时,自有 skill/tool 登记到注册表;公共资源平台内置或开发者上传 |
| 版本 | semver;插件 `depends_on` 用 `^`/`~` 约束 |
| 废弃 | 标记 deprecated,引用方告警;删除前检查无引用 |

## 9. 已确认决策
- [x] §6 skill 组合性:MVP 不支持 + 预留
- [x] §7 来源权限:三类来源 + MVP 默认可复用
- [x] §5.3 skill 执行模型:MVP 先支持"简单 skill(prompt 模板+参数)",复杂子 agent 后续
