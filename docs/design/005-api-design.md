# 005 · API 接口设计

- 文档版本:v0.1(草案)
- 日期:2026-08-11
- 流程阶段:阶段 2 · 设计
- 对应需求:全

---

## 1. 通用约定
- 基础路径 `/api`
- 认证:`Authorization: Bearer <JWT>`(除 register/login)
- 流式:`text/event-stream`(SSE)
- 错误:统一 `{error: {code, message}}`

## 2. 认证(F5)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | `{email, password, role}` |
| POST | `/auth/login` | 返回 `{token, user}` |
| GET | `/auth/me` | 当前用户 |

## 3. 助手市场(F4)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/assistants` | 列表,支持 `?query=&category=` |
| GET | `/assistants/{id}` | 详情(含 manifest 摘要) |

## 4. 对话(F2/F3)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/sessions` | `{plugin_id}` -> `{session_id}` |
| POST | `/chat/sessions/{sid}/messages` | `{content}` -> **SSE 流**(响应消息生成) |
| POST | `/api/sessions/{sid}/blocks/{bid}/interact` | 交互回传(对齐 003 v2.0 §9.1) |
| POST | `/api/sessions/{sid}/messages/regenerate` | regenerate 触发(走流式 SSE) |
| POST | `/api/sessions/{sid}/events` | 副作用事件(thumbs 等) |
| GET | `/chat/sessions` | 我的会话列表 |
| GET | `/chat/sessions/{sid}/messages` | 历史消息 |

### SSE 事件类型(对齐 003 v2.0 §3.3)
| 事件 | data | 说明 |
|------|------|------|
| `delta` | `{block_index, text}` | markdown 块增量(对齐旧 `token`) |
| `block_meta` | `{block_index, type, data, meta?}` | 开新 ContentBlock(替代旧 `component`) |
| `tool_call` | `{kind, name, args, result}` | skill/tool 调用过程 |
| `interact_resp` | `{blocks: ContentBlock[]}` | 交互回传响应(handler 返回的续 block) |
| `done` | `{message_id}` | 本轮结束 |
| `error` | `{code, message}` | 错误 |

## 5. 插件管理(F1,开发者)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/plugins/deploy` | CLI 上传部署(含插件包) |
| GET | `/plugins` | 我的插件 |
| POST | `/plugins/{id}/enable` | 启用 |
| POST | `/plugins/{id}/disable` | 停用 |
| DELETE | `/plugins/{id}` | 卸载 |

## 6. skill/tool 注册表(F7)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/registry/skills` | 公共 skill 列表 |
| GET | `/registry/tools` | 公共 tool 列表 |
| GET | `/registry/{kind}/{name}` | 详情(含版本) |

## 7. LLM 端点管理(管理员)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/admin/llm-endpoints` | 列表 |
| POST | `/admin/llm-endpoints` | 新增端点 |
| PATCH | `/admin/llm-endpoints/{id}` | 修改/设默认 |

## 8. 说明
- 对话(消息流)走 SSE;**交互回传走 HTTP POST**(003 v2.0 §9):简单、RESTful、不引入双协议复杂度
- 插件部署接口主要供 CLI 调用(带开发者 token)
- 注册表只读对外;写入通过插件部署流程
