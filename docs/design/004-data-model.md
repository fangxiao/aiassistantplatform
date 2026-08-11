# 004 · 数据模型设计

- 文档版本:v0.1(草案)
- 日期:2026-08-11
- 流程阶段:阶段 2 · 设计
- 对应需求:全

---

## 1. ER 概览

```
users 1───* sessions 1───* messages
  │            │
  │            └──* component_instances
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
| 字段 | 类型 | 说明 |
|------|------|------|
| id | text pk | 如 `tool:pdf_parse` |
| kind | enum | tool / skill |
| name | text | |
| version | text | semver |
| source | enum | builtin / shared / private |
| owner_id | fk users? | builtin 为 null |
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
| content | jsonb | 文本或结构化内容 |
| tool_calls | jsonb | LLM 发起的调用 |
| tool_call_id | text | tool 角色消息回填关联 |
| component_id | fk component_instances? | |
| created_at | timestamptz | |

### component_instances
| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid pk | |
| session_id | fk sessions | |
| message_id | fk messages | |
| type | text | text_input / checkbox_group / ... |
| props | jsonb | 渲染参数 |
| result | jsonb? | 用户回传结果 |
| status | enum | pending / submitted |

## 3. 索引
- `sessions(user_id)`、`messages(session_id, created_at)`、`skill_tools(kind, name)`、`plugins(owner_id)`、`component_instances(session_id)`

## 4. 说明
- `messages.content` 用 jsonb:支持纯文本、结构化、混合
- 流式输出不落库中间 token,仅落最终消息
- Redis 缓存活跃会话上下文(减少 DB 读)
