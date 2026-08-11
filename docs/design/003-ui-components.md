# 003 · 富交互组件协议

- 文档版本:v0.1(草案,待确认)
- 日期:2026-08-11
- 流程阶段:阶段 2 · 设计
- 对应需求:F3、vision 特色三

---

## 1. 设计目标
插件可在对话中定义富交互组件(超越纯文本),采用「声明 + 动态实例化」:
- 插件在清单**声明**可用组件类型与 schema
- LLM 在对话中通过结构化输出**实例化**组件
- 前端按 schema 渲染,用户交互**回传** agent

## 2. 组件声明(plugin.yaml)
```yaml
ui_components:
  - type: checkbox_group
    schema: { options: [], label: "" }
  - type: rating
    schema: { max: 5 }
```
MVP 基础类型:`text_input` / `checkbox_group` / `dropdown` / `button` / `rating`

## 3. 组件实例化(动态)【核心机制】
**推荐:把「渲染组件」作为一种伪 tool_call**

- 平台把插件声明的组件类型,以 `render_component` 这个 function 告知 LLM(参数:type、props)
- LLM 判断需要结构化输入时,输出 `tool_call: render_component({type, props})`
- 平台**拦截**该 tool_call:不执行,而是下发组件实例给前端渲染,挂在当前助手消息后
- 与真正的 skill/tool 调用共用 function-calling 机制,只是平台分流处理

**优点**:统一结构化输出机制;LLM 决定时机与参数(动态);组件类型受插件声明约束(可控)。

## 4. 渲染
前端 `web/components/interactive` 按 `type` 路由到对应 React 组件,注入 `props`。

## 5. 回传
```
用户填写/点击 -> 提交
POST /api/chat/sessions/{sid}/components/{cid}/submit { result }
-> 平台把 result 作为 user 消息(或 tool 结果)回填 agent -> 继续对话
```

## 6. 与对话流集成
agent 一次推理可同时产出:文本(token 流)、skill/tool 调用(执行)、render_component(渲染组件)。三者都通过 OpenAI 协议的结构化输出,平台分流。

## 7. 待确认决策(方向性)
- [ ] §3 组件实例化用「render_component 伪 tool」(推荐,统一机制)vs 独立 JSON schema 解析?
- [ ] §2 MVP 组件类型集合 `text_input/checkbox_group/dropdown/button/rating` 是否够用?要增减吗?
