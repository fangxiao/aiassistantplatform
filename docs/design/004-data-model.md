# 004 · 数据模型设计

- 文档版本:v0.1(草案)
- 日期:2026-08-11
- 流程阶段:阶段 2 · 设计
- 对应需求:全

---

## 1. ER 概览

```
users 1───* sessions 1───* messages(blocks[] 存 ContentBlock 列表)
  │
  └──* plugins 1──* (depends_on) skill_tools(注册表)
                                    ▲
                          platform builtin / shared

llm_endpoints(独立)
```

- **Plugin 即 Assistant**:插件部署后即为可选用助手,不单建 Assistant 表
- **skill_tools 表 = 注册表持久化**(对应 002 §3)

## 2. 表设计

### users
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| email | text unique | |
| password_hash | text | bcrypt |
| role | enum | user / developer |
| created_at | timestamptz | |

### plugins
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| name | text | |
| version | text | semver |
| manifest | jsonb | 完整 plugin.yaml |
| status | enum | active / disabled |
| owner_id | fk users | |
| deployed_at | timestamptz | |

### skill_tools(注册表)
> M2 修订:`id` 为主键之一,实际主键为 `(id, version)` 复合主键——同一资源可登记多个
> semver 版本(002 §8),`depends_on` 按 `^`/`~` 约束解析;`owner_id` 暂为 text,
> M1 引入 users 表后改为 FK。
| 字段 | 类型 | 说明 |
|------|------|------|
| id | text pk | 如 `tool:pdf_parse` |
| version | text pk | semver |
| kind | enum | tool / skill |
| name | text | |
| source | enum | builtin / shared / private |
| owner_id | fk users? | builtin 为 null(M1 后改 FK) |
| schema | jsonb | function 参数/返回 schema |
| impl_path | text | 进程内加载路径 |
| description | text | |

### llm_endpoints
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| name | text | 如 glm-5.2 |
| base_url | text | OpenAI 兼容端点 |
| model | text | |
| api_key_enc | text | 加密存储 |
| is_default | bool | |

### sessions
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| user_id | fk users | |
| plugin_id | fk plugins | |
| title | text | |
| created_at / updated_at | timestamptz | |

### messages
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| session_id | fk sessions | |
| role | enum | user / assistant / tool / system |
| blocks | jsonb | ContentBlock 列表(消息信封,详见 003 v2.0 §3);新消息统一用此字段 |
| content | jsonb | **历史兼容**:旧消息用此字段存纯文本/结构化;新消息不写 |
| tool_calls | jsonb | LLM 发起的调用 |
| tool_call_id | text | tool 角色消息回填关联 |
| created_at | timestamptz | |

### interact_events(交互事件)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| session_id | fk sessions | |
| block_id | text | 对应 messages.blocks[].meta.id |
| kind | enum | interact / thumbs / regenerate |
| action | text | 插件 handler 名(对齐 ADR 0001) |
| value | jsonb | 用户操作值 |
| created_at | timestamptz | |

> 交互控件的 ContentBlock 存在 `messages.blocks[]` 内(与消息共存,不再独立表)。`interact_events` 仅用于审计/反馈/regenerate 等副作用事件(对应设计 003 §9.4)。

## 3. 索引
- `sessions(user_id)`、`messages(session_id, created_at)`、`skill_tools(kind, name)`、`plugins(owner_id)`、`interact_events(session_id, created_at)`

## 4. 说明
- `messages.blocks`(jsonb)是消息信封,存 ContentBlock 列表(对齐 003 v2.0 §3.1)
- `messages.content`(jsonb)**仅用于历史兼容**,新消息不写;前端读取时优先 `blocks`,缺失回退 `content`
- 流式输出不落库中间 token,仅落最终消息(流式过程中 SSE 推到前端)
- Redis 缓存活跃会话上下文(减少 DB 读)
- 旧 `component_instances` 表已废弃,移除(详见设计 003 v2.0 §14 协同清单)
