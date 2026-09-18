# 014 · 动作能力与 MCP 总线设计

- 文档版本:v0.1
- 日期:2026-09-18
- 对应需求:[010-actions-mcp](../requirements/010-actions-mcp.md)

## 1. tool:http_request(通用动作)

- `core/agent/http_action.py`:`run(args)`——args = {method, url, headers?, body?};
  同款 loop 特判分发(无 DB 依赖)。
- 安全链:白名单(`settings.action_http_allowlist`,域名精确匹配,空=禁用)
  → 协议白名单 → SSRF DNS 级拦截(复用 connectors.web._is_public_ip)→
  执行(超时 15s,响应截断 256KB,禁 stream)。
- 拒绝语义:返回 JSON {ok:false, error:原因} 给 LLM(可向用户解释),不抛异常。

## 2. MCP server(手写最小 JSON-RPC,零新依赖)

- `api/mcp.py`:单端点 `POST /api/mcp`(streamable HTTP;server 直接回 JSON 响应,
  规范允许)。Bearer JWT 鉴权(复用 get_current_user)。
- 方法面:
  - `initialize` → {protocolVersion:"2024-11-05", capabilities:{tools:{}}, serverInfo}
  - `notifications/initialized` → 202 无体
  - `tools/list` → platform_kb_search / platform_list_kbs(schema 声明)
  - `tools/call` → {content:[{type:"text",text}], isError?}
- kb_search 身份链:get_current_user → list_visible_kbs(该用户) → ids 作为
  allowed → run_kb_search(M12 执行器,含引用块防护与溯源)。
- Claude Code 配置示例(mcpServers http transport + Authorization header)。

## 3. 任务

| ID | 内容 |
|----|------|
| T17.1 | tool:http_request + 白名单/SSRF + 测试 |
| T17.2 | MCP server(握手/list/call/401)+ 测试(fake embedding 检索) |
| T17.3 | Claude Code 实测接入 + 文档(CLI guide/MCP 配置说明) |

## 4. MCP 接入指南(Claude Code / Cursor)

1. 从工作台「插件连接」弹窗复制平台 token(或 `POST /api/auth/login` 获取);
2. Claude Code 配置(`~/.claude.json` 的 mcpServers 或项目 .mcp.json):

```json
{
  "mcpServers": {
    "agentplatform": {
      "type": "http",
      "url": "http://localhost:8000/api/mcp",
      "headers": { "Authorization": "Bearer <你的token>" }
    }
  }
}
```

3. 重启客户端后即可:"查一下平台知识库里关于连接器的设计"→ 经 platform_kb_search
   返回带溯源的检索结果(按 token 用户的可见库权限)。
