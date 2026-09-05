# 远程开发模式设计文档 (Remote Dev)

- 文档版本: v0.1 (草稿)
- 日期: 2026-08-26
- 流程阶段: 阶段 2 · 设计
- 对应需求: [004-remote-dev.md](../requirements/004-remote-dev.md)
- 依赖设计: 005-api-design.md(API 风格) / 006-plugin-spec.md(插件清单)

## 变更记录
- v0.1(2026-08-26): 初稿。覆盖远程调试会话 + SSE 传输 + CLI 远程模式。

---

## 1. 架构概览

```
┌─────────────────────────┐         ┌───────────────────────────────┐
│  插件开发机 (CLI)        │         │  平台服务端                   │
│                         │  HTTP   │                               │
│  agentplatform dev .    │ ──────→ │  POST /api/plugins/dev-session │
│  --target http://...    │         │  创建调试会话                  │
│                         │         │                               │
│  1. 解析 plugin.yaml    │         │  1. 校验 manifest             │
│  2. 读取 .py 代码       │         │  2. 注册临时 skill/tool       │
│  3. POST 上传 manifest  │         │  3. 返回 session_id           │
│     + 源码              │         │                               │
│                         │  POST  +────────  SSE 流 ───────────┐   │
│  REPL 循环:             │         │   /api/plugins/dev-session/{id}/messages
│  用户输入 → POST        │ ──────────────────────────────────→ │   │
│  SSE 接收 → 打印        │ ←─── delta / tool_call / done ──────│   │
│                         │                                     │   │
│  exit → DELETE          │ ──────→  DELETE 清理资源             │   │
└─────────────────────────┘         └───────────────────────────────┘
```

### 1.1 设计原则

1. **复用现有能力**：远程 dev 的 agent 循环复用 `stream_agent`，SSE 格式复用 `/chat/sessions/{id}/messages` 的事件格式，`PluginManifest` 复用现有模型（已有 `code` 字段）、`register` 复用现有注册表服务。
2. **零侵入**：平台现有生产 API 不做任何修改。远程 dev 是新增独立路由 `/api/plugins/dev-session/*`，不影响已部署插件和现有会话。
3. **临时性**：调试会话的资源和代码是临时的，TTL 超时或主动清理后完全消失，不影响注册表和存储。

---

## 2. API 设计

### 2.1 创建调试会话

```
POST /api/plugins/dev-session
Authorization: Bearer <jwt>

Request body:
{
  "manifest": {
    // PluginManifest 完整结构（与 plugin.yaml 一一对应）
    "name": "my-assistant",
    "version": "0.1.0",
    "model": "deepseek-v4-flash",
    "depends_on": ["tool:pdf_parse@^1.0", "skill:summarize@^1.0"],
    "skills": [
      {
        "id": "skill:my-assistant_demo",
        "file": "skills/demo.py",
        "code": "# ... Python 源码 ...",   // ← 代码直接嵌入
        "description": "示例技能",
        "schema": { "type": "object", ... }
      }
    ],
    "tools": [
      {
        "id": "tool:my-assistant_echo",
        "file": "tools/demo.py",
        "code": "# ... Python 源码 ..."
      }
    ]
  }
}
```

**校验逻辑**（复用部署的 `validate_manifest`，新增 `code` 非空校验）：
1. 调用 `validate_manifest(manifest)` — 与部署一致
2. 检查每个 skill/tool 的 `code` 字段非空 — 新增
3. 调用 `check_dependencies(session, depends_on)` — 依赖解析同部署
4. 校验通过 → 创建会话；失败 → 422 结构化错误

**响应**：
```json
{
  "ok": true,
  "session_id": "uuid-string",
  "messages_url": "http://192.168.1.100:8000/api/plugins/dev-session/uuid-string/messages",
  "ttl_seconds": 1800,
  "resources": [
    "tool:pdf_parse",
    "skill:summarize",
    "skill:my-assistant_demo",
    "tool:my-assistant_echo"
  ]
}
```

### 2.2 发送消息并接收 SSE 流

```
POST /api/plugins/dev-session/{session_id}/messages
Content-Type: application/json
Authorization: Bearer <jwt>

{
  "content": "你好，请介绍一下你的功能"
}
```

**响应**：`text/event-stream`，事件格式与 `/chat/sessions/{sid}/messages` 完全一致：

```
event: delta
data: {"block_index": 0, "text": "你好！我是"}

event: tool_call
data: {"kind": "skill", "name": "skill:my-assistant_demo", "args": {...}, "result": "..."}

event: delta
data: {"block_index": 0, "text": "我的功能包括..."}

event: done
data: {"message_id": "dev-session-xxxx"}
```

**错误响应**（流内）：
```
event: error
data: {"code": "session_expired", "message": "调试会话已过期"}
```

### 2.3 清理调试会话

```
DELETE /api/plugins/dev-session/{session_id}
Authorization: Bearer <jwt>

Response: { "ok": true }
```

**清理动作**：
1. 删除 `~/.agentplatform/dev_sessions/{session_id}/` 目录（临时代码文件）
2. 从注册表删除该会话注册的临时 private 资源（`owner_id == f"dev_session:{session_id}"`）
3. 删除会话内存记录

### 2.4 心跳续期

```
POST /api/plugins/dev-session/{session_id}/heartbeat
Authorization: Bearer <jwt>

Response: { "ok": true, "ttl_seconds": 1800 }
```

每次发消息自动续期；心跳端点供 CLI 空闲时保活。

---

## 3. 平台端实现

### 3.1 新增 / 修改文件

| 文件 | 操作 | 职责 |
|------|------|------|
| `agentplatform/core/plugin/dev_session.py` | 新建 | DevSession 数据模型 + 管理器 + TTL 清理 |
| `agentplatform/api/plugins.py` | 修改 | 新增 `/dev-session` 路由组 |
| `agentplatform/config.py` | 修改 | 新增 `dev_session_ttl` 等配置项 |

### 3.2 DevSession 数据模型

```python
@dataclass
class DevSession:
    """调试会话（内存态，不落 PostgreSQL）。"""
    session_id: str            # UUID
    user_id: str               # JWT sub
    manifest: PluginManifest   # 原始 manifest
    resource_ids: list[str]    # 可用资源 id 列表
    ttl: int = 1800            # TTL 秒
    created_at: float          # time.monotonic()
    last_active: float         # 最后一次活动时间
    history: list[dict]        # 对话历史（内存维护，结束即丢弃）
```

### 3.3 DevSession 管理器

```python
class DevSessionManager:
    """进程内调试会话注册表（单例内存存储）。"""

    def __init__(self) -> None:
        self._sessions: dict[str, DevSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, user_id: str, manifest: PluginManifest,
                     resource_ids: list[str]) -> DevSession: ...

    async def get(self, session_id: str) -> DevSession | None: ...

    async def delete(self, session_id: str) -> None: ...

    async def touch(self, session_id: str) -> int:
        """刷新 last_active，返回剩余 ttl_seconds。"""

    async def reap_expired(self) -> int:
        """清理过期会话，返回清理数量。"""


# 进程内单例
dev_manager = DevSessionManager()
```

### 3.4 注册临时资源

创建会话时，将插件私有 skill/tool 代码写入临时目录并注册：

```python
async def _register_dev_resources(
    db: AsyncSession,
    manifest: PluginManifest,
    session_dir: Path,
) -> list[str]:
    """把插件私有 skill/tool 代码写入临时目录并注册到注册表。返回资源 id 列表。"""
    resource_ids: list[str] = []
    for kind, section in ((SkillToolKind.skill, manifest.skills),
                          (SkillToolKind.tool, manifest.tools)):
        for res_def in section:
            # 1. 写入临时代码文件
            file_path = session_dir / res_def.file.lstrip("./")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(res_def.code or "", encoding="utf-8")

            # 2. 注册到注册表，impl_path 指向临时文件（复用 resolve_impl 加载路径）
            await register(
                db,
                resource_id=res_def.id,
                kind=kind,
                name=res_def.id.split(":", 1)[1],
                version=manifest.version,
                source=SkillToolSource.private,
                schema_=res_def.schema_ or {"parameters": {"type": "object"}},
                impl_path=str(file_path.resolve()),
                description=res_def.description,
                owner_id=f"dev_session:{session_id}",  # 与会话绑定，便于清理
            )
            resource_ids.append(res_def.id)
    await db.commit()
    return resource_ids
```

**清理时删除方式**：
```python
await db.execute(
    sa.delete(SkillTool).where(
        SkillTool.owner_id == f"dev_session:{session_id}")
)
```

### 3.5 SSE 对话流

```python
async def dev_session_chat_stream(
    db: AsyncSession,
    dev_session: DevSession,
    user_message: str,
) -> AsyncIterator[dict]:
    """远程调试的 SSE 事件流（复用 stream_agent 循环）。"""
    from agentplatform.core.llm.client import OpenAIClient
    from agentplatform.core.llm.router import resolve_endpoint

    # 1. 解析 LLM 端点（与 /chat/sessions 同逻辑）
    model = dev_session.manifest.model
    client = await make_llm_client(db, model)

    # 2. 追加用户消息到历史
    dev_session.history.append({"role": "user", "content": user_message})

    # 3. 调用 stream_agent，前文为历史（不含本条消息）
    text_parts: list[str] = []
    async for event in stream_agent(
        db, client,
        resource_ids=dev_session.resource_ids,
        user_message=user_message,
        history=dev_session.history[:-1],
        owner_id=dev_session.user_id,
    ):
        if event.type == "delta" and event.text:
            text_parts.append(event.text)
            yield {"event": "delta", "data": {"text": event.text}}
        elif event.type == "tool_call" and event.tool_trace is not None:
            t = event.tool_trace
            yield {"event": "tool_call", "data": {
                "kind": t.id.split(":", 1)[0],
                "name": t.id,
                "args": t.args,
                "result": t.result,
            }}

    # 4. 最终结果写入历史（内存态）
    full_text = "".join(text_parts)
    dev_session.history.append({"role": "assistant", "content": full_text})
    yield {"event": "done", "data": {"ok": True}}
```

### 3.6 TTL 清理定时任务

通过 FastAPI `lifespan` 启动后台任务：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_ttl_reaper())
    yield
    task.cancel()


async def _ttl_reaper() -> None:
    """每 60 秒清理一次过期调试会话。"""
    while True:
        cleaned = await dev_manager.reap_expired()
        if cleaned:
            logger.info("已清理 %d 个过期调试会话", cleaned)
        await asyncio.sleep(60)
```

`reap_expired()` 的具体清理动作：
1. 遍历会话，找 `monotonic() - last_active > ttl` 的过期项
2. 删除 `~/.agentplatform/dev_sessions/{session_id}/` 目录
3. 从注册表删除 `owner_id == f"dev_session:{session_id}"` 的资源
4. 从 `dev_manager._sessions` 中移除

### 3.7 路由注册

修改 `agentplatform/api/plugins.py`：

```python
@router.post("/dev-session", status_code=201, response_model=DevSessionResponse)
async def create_dev_session(
    payload: DevSessionRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DevSessionResponse: ...

@router.post("/dev-session/{session_id}/messages")
async def send_dev_message(
    session_id: str,
    payload: DevSessionMessageRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse: ...

@router.delete("/dev-session/{session_id}")
async def delete_dev_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict: ...

@router.post("/dev-session/{session_id}/heartbeat")
async def heartbeat_dev_session(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict: ...
```

每个端点首先校验 `dev_session.user_id == str(user.id)`（会话归属）。

---

## 4. CLI 端实现

### 4.1 修改 `agentplatform/cli/dev.py`

新增远程模式入口 `run_remote_dev_loop()`，与现有 `run_dev_loop()` 并列（本地逻辑不动）。

```python
async def run_remote_dev_loop(root: Path, target: str) -> None:
    """远程 dev：上传插件 → 远程平台执行 agent 循环 → SSE 流回显。"""
    import httpx

    token = _load_or_prompt_token()          # 见 4.2
    manifest = _build_dev_manifest(root)     # 见 4.3
    resp = httpx.post(
        f"{target}/api/plugins/dev-session",
        json={"manifest": manifest},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code != 201:
        _print_dev_error(resp)               # 结构化错误展示
        return
    session = resp.json()
    print(f"🌐 远程调试模式: {target}")
    print(f"📦 已挂载资源 ({len(session['resources'])}): {', '.join(session['resources'])}")
    print("💡 输入 exit 退出")

    try:
        while True:
            text = input("你> ").strip()
            if text.lower() in ("exit", "quit"):
                break
            await _remote_chat_once(target, session["session_id"], token, text)
    finally:
        # 退出时主动清理远程会话
        httpx.delete(
            f"{target}/api/plugins/dev-session/{session['session_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
```

### 4.2 Token 获取

CLI 本地配置文件 `~/.agentplatform/config.json` 增加 `token` 字段：

```json
{
  "target": "http://192.168.1.100:8000",
  "token": "<jwt>"
}
```

读取优先级：`AGENTPLATFORM_TOKEN` 环境变量 > `~/.agentplatform/config.json` > 交互提示输入。

### 4.3 manifest 组装（含源码）

```python
def _build_dev_manifest(root: Path) -> dict:
    """读取 plugin.yaml 并注入各 skill/tool 的源码。"""
    manifest = yaml_io.load_manifest(root / "plugin.yaml")
    for section in ("skills", "tools"):
        for res in manifest.get(section, []):
            file_path = root / res["file"]
            if file_path.exists():
                res["code"] = file_path.read_text(encoding="utf-8")
    return manifest
```

### 4.4 `cmd_dev` 分支（`agentplatform/cli/main.py`）

```python
def cmd_dev(args: argparse.Namespace) -> int:
    target = get_target_url(args)
    parsed = urlparse(target)
    is_remote = parsed.hostname not in ("localhost", "127.0.0.1", "0.0.0.0", "")

    if is_remote:
        import asyncio
        from agentplatform.cli.dev import run_remote_dev_loop
        asyncio.run(run_remote_dev_loop(Path(args.path), target))
    else:
        # 现有本地逻辑（OPENAI_API_KEY 校验 + run_dev_loop）不变
        ...
    return 0
```

`dev` 子命令新增 `--target` 参数（解析目标复用 `get_target_url`）。

### 4.5 SSE 流式接收

```python
async def _remote_chat_once(target: str, session_id: str, token: str, text: str) -> None:
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{target}/api/plugins/dev-session/{session_id}/messages",
            json={"content": text},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        ) as resp:
            if resp.status_code != 200:
                _print_dev_error(resp)
                return
            event_type = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                    if event_type == "delta":
                        print(data["text"], end="", flush=True)
                    elif event_type == "tool_call":
                        print(f"\n  ⚙ {data['name']} -> {data['result'][:60]}")
                    elif event_type == "done":
                        print()
                    elif event_type == "error":
                        print(f"\n  ❌ {data['message']}")
```

### 4.6 REPL 终端效果

```
🌐 远程调试模式: http://192.168.1.100:8000
📦 已挂载资源 (4): tool:pdf_parse, skill:summarize, skill:my-assistant_demo, tool:my-assistant_echo
💡 输入 exit 退出

你> 你好
🤖 你好！我是 my-assistant，我的功能是...
  ⚙ skill:my-assistant_demo -> 分析完成
我的功能包括...

你> exit
✅ 远程调试会话已清理
```

---

## 5. 错误处理

| 场景 | HTTP 状态码 | 响应 |
|------|-------------|------|
| manifest 不合法 | 422 | `{error: {code: "validation_error", message: "...", details: [...]}}` |
| 依赖不存在 | 422 | `{error: {code: "dependency_not_found", message: "...", missing: [...]}}` |
| 调试会话不存在 | 404 | `{error: {code: "not_found", message: "调试会话不存在"}}` |
| 调试会话已过期 | 410 | `{error: {code: "session_expired", message: "调试会话已过期"}}` |
| 超出会话数量限制 | 429 | `{error: {code: "too_many_sessions", message: "已存在活跃调试会话"}}` |
| 认证失败 | 401 | `{error: {code: "unauthorized", message: "..."}}` |
| LLM 调用失败 | SSE error 事件 | `{event: "error", data: {code: "agent_error", message: "..."}}` |

---

## 6. 安全考量

### 6.1 鉴权

所有远程 dev API 均需 `Bearer JWT`（`get_current_user`），与现有生产 API 一致。`dev-session/{id}/*` 校验 `dev_session.user_id == str(user.id)`（会话归属）。

### 6.2 资源隔离

- 调试会话注册的资源 `owner_id == f"dev_session:{session_id}"`，不与已部署插件冲突
- agent 循环只加载该会话的 `resource_ids`，不加载其他插件的 private 资源
- `source = private`，不影响 `builtin` / `shared` 资源

### 6.3 代码安全

- 上传代码写入 `~/.agentplatform/dev_sessions/{session_id}/`，与会话绑定
- 清理时删除整个目录，不留残余
- 代码只在平台进程内加载执行，不跨用户暴露

### 6.4 限流

- 同一用户最多同时 1 个活跃调试会话
- 每个会话最多 100 次消息交互（防失控）
- 消息内容最大 10000 字符

---

## 7. 多 worker 注意事项

当前 POC 单 worker 运行，`DevSessionManager` 为进程内内存存储。

多 worker 场景需要：
1. 将 DevSession 存储迁移到 Redis（共享状态）
2. 或使用 sticky session（LB 将同一 session_id 路由到同一 worker）
3. 或将调试会话状态持久化到 PostgreSQL（增加清理复杂度）

**MVP 不做**：POC 阶段单 worker，`docker-compose.yml` 中 `api` 服务 `replicas: 1`。

---

## 8. 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `agentplatform/core/plugin/dev_session.py` | 新建 | DevSession 数据模型 + 管理器 |
| `agentplatform/core/plugin/__init__.py` | 修改 | 导出 dev_session |
| `agentplatform/api/plugins.py` | 修改 | 新增 /dev-session 路由组 |
| `agentplatform/config.py` | 修改 | 新增 `dev_session_ttl` 等配置项 |
| `agentplatform/cli/dev.py` | 修改 | 新增 `run_remote_dev_loop()` |
| `agentplatform/cli/main.py` | 修改 | `cmd_dev` 区分远程/本地模式 |

---

## 9. 与现有设计的关系

| 引用关系 | 说明 |
|----------|------|
| [005-api-design.md](./005-api-design.md) | 统一错误信封 `{error: {code,message}}` |
| [006-plugin-spec.md](./006-plugin-spec.md) | PluginManifest + ResourceDef（已有 `code` 字段） |
| [001-architecture.md](./001-architecture.md) | Client-Server 架构，CLI 通过 HTTP 与平台通信 |
| `stream_agent` 循环 | 复用，无修改 |
| SSE 事件格式 | 复用 `/chat/sessions/{id}/messages` 格式 |
| `register()` | 复用，使用临时 impl_path |
| `resolve_impl()` | 复用，根据 impl_path 加载临时文件 |
| [004-remote-dev.md](../requirements/004-remote-dev.md) | 本文档实现该需求的全部条款 |