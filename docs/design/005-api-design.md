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
| POST | `/chat/sessions/{sid}/messages` | `{content}` -> **SSE 流** |
| POST | `/chat/sessions/{sid}/components/{cid}/submit` | `{result}` -> **SSE 流** |
| GET | `/chat/sessions` | 我的会话列表 |
| GET | `/chat/sessions/{sid}/messages` | 历史消息 |

### SSE 事件类型
| 事件 | data | 说明 |
|------|------|------|
| `token` | `{text}` | 文本片段(流式) |
| `tool_call` | `{kind, name, args, result}` | skill/tool 调用过程 |
| `component` | `{cid, type, props}` | 渲染组件 |
| `done` | `{message_id}` | 本轮结束 |
| `error` | `{message}` | 错误 |

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
- 对话与组件回传均走 SSE,前端统一事件处理
- 插件部署接口主要供 CLI 调用(带开发者 token)
- 注册表只读对外;写入通过插件部署流程
