# 需求文档 · 动作能力与 MCP 总线(M17 · Actions & MCP)

- 文档版本:v0.1(草案,待评审)
- 日期:2026-09-18
- 流程阶段:阶段 1 · 需求
- 背景:平台 agent 已"能说、能查、能记、能定时",但**不能动手**——发飞书消息、调
  内部系统 API、写工单都做不到。同时平台的能力(知识库检索/agent)也无法被外部 AI
  客户端(Claude Code/Cursor)消费。本里程碑补上这两个生态级缺口:
  **① agent 的通用动作能力;② 平台作为 MCP server 对外暴露能力**。

---

## 1. 问题陈述

1. **agent 无动作能力**:对话中用户说"调内部接口查一下订单状态",agent 只能回答
   "我做不到"。竞品生态(豆包内置插件/WorkBuddy 办公集成)均有动作能力。
2. **平台能力不可被外部消费**:用户在 Claude Code/Cursor 里工作时,无法直接查询
   平台知识库——平台知识资产的消费入口只有自家 WebUI,价值半径受限。

## 2. 目标

1. **`tool:http_request` 通用动作工具**:agent 可调用外部 HTTP API(发消息/查数据),
   受**域名白名单**与 SSRF 防护约束——白名单为空时工具禁用(安全默认);
2. **MCP server**:平台以 Model Context Protocol 对外暴露能力,外部 AI 客户端
   (Claude Code/Cursor/任意 MCP 客户端)可经 HTTP+Bearer token 调用:
   - `platform_kb_search`:按 token 所属用户的知识库权限检索
   - `platform_list_kbs`:列出该用户可见的知识库
3. 安全默认:两者默认关闭/最小暴露,由管理员显式开启。

## 3. 用户故事

- **U1 动作白名单配置**:管理员在环境变量配置允许的域名
  (`ACTION_HTTP_ALLOWLIST=open.feishu.cn,api.internal.corp`);未配置时
  tool:http_request 对任何请求返回"未启用"提示。
- **U2 agent 执行动作**:对话中"给飞书群发一条消息"→ agent 调
  tool:http_request(method=POST, url=https://open.feishu.cn/...)→ 执行并汇报结果;
  白名单外域名被拒绝并说明原因(SSRF 内网地址同样拦截)。
- **U3 外部客户端接入**:用户从工作台「插件连接」弹窗获取 token 与 MCP 地址,在
  Claude Code 配置 MCP server;之后在 Claude Code 里"查平台知识库里关于连接器的设计"
  → 经 platform_kb_search 返回带溯源的检索结果。
- **U4 身份与权限**:MCP 调用以 Bearer token(JWT)身份执行——检索范围 = 该用户
  可见的知识库(M12 权限同源);无 token 401。
- **U5 可观测**:http_request 调用与 MCP 调用记录结构化日志(谁/何时/调了什么)。

## 4. 验收标准

1. 白名单配置 `open.feishu.cn` 后,agent 在对话中成功 POST 该域名并复述响应;
   未配置时工具返回"未启用"而非报错崩溃;
2. 白名单外域名/内网 IP/169.254 元数据地址均被拒绝,agent 收到明确拒绝原因;
3. Claude Code(或任意 MCP 客户端)完成 MCP 握手,tools/list 列出 2 个工具,
   tools/call platform_kb_search 返回该用户可见库的检索结果(带文档名与来源);
4. 无效/缺失 token → 401;A 用户的 token 检索不到 B 用户的 private 库内容;
5. 全量测试回归通过;新增功能单测覆盖(MockTransport)。

## 5. 非功能约束

- **MCP 实现不引入新依赖**:手写最小 JSON-RPC 端点(协议面窄:initialize/
  tools/list/tools/call,streamable HTTP 传输)——避免引入 mcp SDK 的依赖树;
  协议兼容性以 Claude Code 实测为准;
- 复用既有安全件:SSRF 判定(M13 web.py 的 _is_public_ip)、JWT 鉴权、
  kb_search 执行器(M12,含权限收口与 [引用块] 注入防护);
- http_request 不支持流式,响应体上限 256KB,超时 15s。

## 6. 范围外(后续里程碑)

- 预置 SaaS 动作连接器(飞书/企微 SDK 化封装,带 OAuth)——本期通用 HTTP 动作
- MCP resources/prompts 能力(仅 tools);MCP stdio 传输
- 动作市场/插件化动作包;调用配额计费
- 写操作的二次确认流(危险动作 input.confirm 确认后执行)——P1 候选

## 7. 分期建议

- **P0**:tool:http_request(白名单+SSRF+大小/超时约束)+ MCP server
  (kb_search/list_kbs,JWT 鉴权)+ Claude Code 实测接入 + 测试
- **P1**:更多 MCP 工具(todo/memory 写)、动作审计面板、写操作确认流
- **P2**:预置连接器、MCP resources
