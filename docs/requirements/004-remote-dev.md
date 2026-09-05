# agentplatform 远程开发 (Remote Dev) 需求文档

- 文档版本: v0.1 (草稿)
- 日期: 2026-08-26
- 流程阶段: 阶段 1 · 需求(增量)
- 对应主需求: [001-product-requirements.md](./001-product-requirements.md) §F1(插件开发工作流)
- 对应设计: (待设计)

## 变更记录
- v0.1(2026-08-26): 初稿。基于插件开发者在局域网内跨机器开发的场景。

---

## 1. 背景与目标

### 1.1 背景

当前 `agentplatform dev .` 和 `agentplatform chat .` 完全本地运行：
- 使用本地 SQLite 数据库
- 使用本地 LLM 客户端（从环境变量读取端点）
- 所有 agent 循环、资源执行在本地进程完成

但实际开发场景中，**插件开发者与平台服务不在同一台机器**（仅在同一个局域网）。这意味着：

- 插件机（开发机）上通常没有数据库、没有 LLM 端点配置
- 平台机（服务端）上运行着 PostgreSQL、Redis、LLM 端点配置
- 开发者希望插件**代码在本地编辑**，但 `dev` 调试时**运行时走远程平台**

当前 `deploy` / `update` / `registry` 已支持 `--target` 远程访问，但 `dev` 和 `chat` 不支持，形成工作流断裂。

### 1.2 目标

- 插件开发者可在本地编辑代码，通过 `agentplatform dev . --target http://192.168.1.100:8000` 远程调试
- 远程平台负责：LLM 端点调用、agent 循环调度、资源注册表提供
- 插件私有的 skill/tool 代码**上传到远程平台临时执行**，无需在平台机持久化部署
- 调试结束后自动清理远程临时资源
- 工作流连贯：`validate(本地) → test(本地) → dev --target(远程) → deploy(远程)`

### 1.3 非目标（MVP 不做）

- 不做实时文件同步 / 热重载（每次 `dev` 启动时一次性上传）
- 不做多开发者同时调试同一插件
- 不做 TLS / 加密传输（局域网 MVP 假设）
- 不做断线重连（网络断开 = 调试会话终止）
- 不做跨网段 / 跨互联网（局域网即可）

---

## 2. 用户角色

| 角色 | 核心关切 |
|------|----------|
| 插件开发者 | 在本地开发机上写代码，通过远程平台调试，无需在本地搭建平台基础设施 |
| 平台管理员 | 确保远程调试会话不影响生产数据，调试结束后自动清理 |

---

## 3. 核心概念

| 概念 | 定义 |
|------|------|
| **Dev Session（调试会话）** | 平台端临时创建的调试环境，关联一个插件版本、一组临时资源，有生存期 TTL |
| **插件代码上传** | CLI 将插件工程的 Python 实现文件通过 HTTP 上传到平台，平台临时存储并加载执行 |
| **远程调试流** | CLI 连到远程平台，发送消息 → 平台执行 agent 循环（含插件私有 skill/tool）→ SSE 流回 CLI |
| **TTL 自动清理** | 调试会话超时（如 30 分钟无活动）后，平台自动删除临时资源与代码 |

---

## 4. 功能需求

### F-RD-1 远程调试会话管理

- F-RD-1.1 CLI 支持 `agentplatform dev . --target <url>` 启动远程调试模式
- F-RD-1.2 CLI 向远程平台 `POST /api/plugins/dev-session` 创建调试会话
- F-RD-1.3 请求体包含：插件 manifest（含 depends_on、skills、tools 声明）+ 各 skill/tool 文件的代码内容
- F-RD-1.4 平台验证 manifest（同本地 validate 逻辑），校验 depends_on 依赖存在
- F-RD-1.5 验证通过 → 返回 `session_id` + `ws_url`（WebSocket 连接地址）
- F-RD-1.6 验证失败 → 返回结构化错误，CLI 直接展示给开发者
- F-RD-1.7 调试会话有默认 TTL=30 分钟，每次交互刷新 TTL
- F-RD-1.8 CLI 退出时主动 `DELETE /api/plugins/dev-session/{session_id}` 清理

### F-RD-2 远程调试对话

- F-RD-2.1 CLI 通过 **SSE 流** 与远程平台交互：POST 消息 → 平台返回 SSE 事件流
- F-RD-2.2 协议：CLI POST `{"content": "你好"}`，平台返回 `delta` / `tool_call` / `done` 事件流（与现有 `/chat/sessions/{sid}/messages` 的 SSE 事件格式完全兼容）
- F-RD-2.3 平台端复用现有 `stream_agent` 循环，将插件私有资源（代码已上传）纳入 resource_ids
- F-RD-2.4 平台端执行插件私有 skill/tool 时，从临时存储加载代码执行（与已部署插件走同一路径 `resolve_impl`）
- F-RD-2.5 平台端执行 builtin/shared 资源时，走现有注册表（与生产一致）
- F-RD-2.6 对话历史由平台端维护（内存中，调试会话结束即丢弃）

### F-RD-3 远程 registry 查询

- F-RD-3.1 已有 `agentplatform registry --target <url>` 支持远程拉取注册表，保持不动
- F-RD-3.2 远程 dev 模式下，CLI 自动在启动时拉取远程注册表，展示可用资源列表

### F-RD-4 CLI 端体验

- F-RD-4.1 `agentplatform dev . --target <url>` 与本地 `dev` 的命令行交互体验一致（REPL、`exit` 退出）
- F-RD-4.2 输出格式与本地 dev 一致，仅增加一行提示：`🌐 远程调试模式: http://192.168.1.100:8000`
- F-RD-4.3 如果 `--target` 未指定，回退到本地 dev 模式（向后兼容）

### F-RD-5 安全与清理

- F-RD-5.1 调试会话需要 Bearer token 鉴权（复用现有 JWT 体系）
- F-RD-5.2 平台端限制调试会话只能访问 `builtin` / `shared` 资源，不能访问其他插件的 `private` 资源
- F-RD-5.3 TTL 超时后平台自动清理：删除临时代码文件、删除调试会话记录
- F-RD-5.4 平台端限制每个用户同时最多 1 个活跃调试会话

---

## 5. 非功能需求

- **延迟**: 远程 dev 较本地 dev 增加网络往返（局域网 < 1ms），LLM 调用延迟不变（LLM 调用占主导）
- **资源隔离**: 调试会话的临时资源不影响已部署插件的注册表数据
- **可观测**: 平台端对调试会话的每次 tool_call 和 LLM 调用记录结构化日志，标注 `session_type=dev`
- **兼容性**: 远程 dev 的 agent 行为与部署后一致（同一套 `stream_agent` 循环）

---

## 6. 验收标准

- [ ] 插件机无本地 PostgreSQL、无 LLM 端点配置，通过 `agentplatform dev . --target http://192.168.1.100:8000` 成功启动 REPL 调试
- [ ] 远程调试中，插件私有 skill/tool 可被 LLM 正确调用并返回结果
- [ ] 远程调试中，插件 `depends_on` 的 builtin 资源（如 `skill:summarize`）可被正常调用
- [ ] 远程调试中，LLM 流式输出正确显示在 CLI 终端
- [ ] CLI 退出后，平台端调试会话资源自动清理
- [ ] TTL 超时后，再次发送消息返回错误提示"调试会话已过期"
- [ ] 不指定 `--target` 时，`dev` 行为与之前完全一致（本地模式）

---

## 7. 决策状态

### 7.1 已确认（本文档锁定）
- ✅ 远程 dev 走 **SSE 流**（POST 请求返回 SSE，与生产 `/chat/sessions/{sid}/messages` 完全一致），不新建 WebSocket 传输层
- ✅ 插件代码启动时一次性上传，不做实时同步
- ✅ 调试会话有 TTL，超时自动清理
- ✅ 对话历史仅在内存中维护，不落库
- ✅ 同一用户最多 1 个活跃调试会话
- ✅ 远程 dev 与本地 dev 的 CLI 交互体验一致
- ✅ `--target` 未指定时回退到本地 dev 模式
- ✅ MVP 只做 `dev --target`；`chat`（单轮后台调用）保持本地运行，后续按需再加

### 7.2 留待设计
- 是否需要支持 `--target` 自动发现（如 mDNS / 广播）— 留 v0.2
- 调试会话是否支持多人协作（如共享给同事查看）— 留后续版本
- 是否支持断线重连（当前终止即结束）— 留后续版本
- 是否支持 `--debug` 模式输出更详细的平台端日志 — 留设计阶段

### 7.3 与 001 的关系
- 本文档是对 001 §F1（插件开发工作流）中 `dev` 命令的远程扩展
- 001 §F1.4（本地 dev 流程）不变，新增远程模式作为替代

---

## 8. API 设计草案（待设计阶段细化）

### POST /api/plugins/dev-session
```
请求体:
{
  "manifest": {          // 完整插件 manifest
    "name": "my-assistant",
    "version": "0.1.0",
    "model": "deepseek-v4-flash",
    "depends_on": ["tool:pdf_parse@^1.0", "skill:summarize@^1.0"],
    "skills": [
      {"id": "skill:my-assistant_demo", "file": "skills/demo.py", "code": "..."}
    ],
    "tools": [
      {"id": "tool:my-assistant_echo", "file": "tools/demo.py", "code": "..."}
    ]
  }
}

响应:
{
  "session_id": "uuid",
  "post_url": "http://192.168.1.100:8000/api/plugins/dev-session/{session_id}/messages",
  "ttl_seconds": 1800,
  "resources": ["tool:pdf_parse", "skill:summarize", "skill:my-assistant_demo", "tool:my-assistant_echo"]
}
```

### POST /api/plugins/dev-session/{session_id}/messages
```
请求体: {"content": "你好"}
响应: text/event-stream (SSE)
  事件流: {"event": "delta", "data": {"text": "你好！"}}
          {"event": "tool_call", "data": {"tool_trace": {...}}}
          {"event": "done"}
(与现有 /chat/sessions/{sid}/messages 的 SSE 事件格式完全一致)
```

### DELETE /api/plugins/dev-session/{session_id}
```
响应: {"ok": true}
```

### 发送消息接口的 SSE 事件格式
```
POST /api/plugins/dev-session/{sid}/messages
请求体: {"content": "你好"}
响应: text/event-stream

event: delta
data: {"text": "你好！"}

event: tool_call
data: {"kind": "tool", "name": "tool:my-assistant_echo", "args": {...}, "result": "..."}

event: done
data: {"ok": true}
```

### 平台端已上传的代码存储目录
```
~/.agentplatform/dev_sessions/{session_id}/skills/demo.py
~/.agentplatform/dev_sessions/{session_id}/tools/demo.py
```
(与已部署插件存储目录 `~/.agentplatform/installed_plugins/` 隔离)

---

## 9. 实现映射

| 需求章节 | 对应实现模块 |
|----------|--------------|
| F-RD-1 调试会话管理 | 新增 `agentplatform/core/plugin/dev_session.py` + `agentplatform/api/plugins.py` 新增路由 |
| F-RD-2 远程调试对话 | 新增 `agentplatform/api/plugins.py` WebSocket 路由 + 复用 `core/agent/loop.py` |
| F-RD-3 远程 registry | 已有 `agentplatform/cli/main.py` cmd_registry 不变 |
| F-RD-4 CLI 端体验 | 修改 `agentplatform/cli/dev.py`，新增 `--target` 参数分支 |
| F-RD-5 安全与清理 | 设置 TTL + 定时清理逻辑 + JWT 鉴权复用 |