# 任务拆解

- 文档版本:v0.1
- 日期:2026-08-11
- 流程阶段:阶段 3 · 任务拆解
- 依据:设计文档 001-006

---

## 1. 概述
基于设计文档,拆解为 M0-M10 共 11 个里程碑、约 40 个任务。每个任务标注**依赖**与**优先级**:
- **P0**:MVP 核心链路,必须先做
- **P1**:MVP 完善,核心链路跑通后补
- **P2**:后续/打磨

## 2. 依赖关系总览

```
M0(脚手架)
  ├─> M2(注册表) ─┐
  ├─> M3(LLM网关) ─┼─> M5(agent运行时) ─> M6(对话API) ─> M8.1(对话页) ─┐
  └─> M4(插件加载) ─┘                                                  ├─> M10(集成)
                                  M9(SDK+CLI) 依赖 M2/M4/M5/M6 ────────┘
M1(认证)、M7(富交互)、M8.2-8.4(其余前端) 在核心链路后并行补齐
```

## 3. 里程碑与任务

### M0 · 项目脚手架与基础设施(P0)
| ID | 任务 | 依赖 |
|----|------|------|
| T0.1 | 后端 `agentplatform/` 结构 + Python 环境(uv)+ 依赖(FastAPI/SQLAlchemy/Pydantic 等) | - |
| T0.2 | 前端 `web/` 结构 + Next.js 14 + Tailwind + TypeScript | - |
| T0.3 | `docker-compose`(pg/redis/api/web 四服务) | T0.1, T0.2 |
| T0.4 | 数据库基础:SQLAlchemy base + Alembic 迁移框架 | T0.1 |

> **M0 状态:已完成(2026-08-13)**。实现采用 uv 单项目(pyproject 在仓库根),后端包名定为 `agentplatform`(原 `platform` 与 Python stdlib `platform` 模块冲突,会破坏 SQLAlchemy 导入;已同步 001/006/003 等文档)。前端为手工脚手架(避免 create-next-app 版本漂移)。docker-compose 仅验证 `config`;`up` 运行时验证需 docker daemon。

### M1 · 认证与用户(P1)
| ID | 任务 | 依赖 |
|----|------|------|
| T1.1 | `users` 表迁移 | T0.4 |
| T1.2 | 认证服务(注册/登录/bcrypt/JWT/角色) | T1.1 |
| T1.3 | 认证 API(`/auth/*`)+ 中间件 | T1.2 |
| T1.4 | 前端登录/注册页 | T1.3, T0.2 |

> **M1 状态:已完成(2026-08-15)**。
> `users` 表迁移 `f5dc28be702f` (email 唯一, password_hash, role 默认 user);
> 密码哈希使用 `passlib[bcrypt]` / `bcrypt`，JWT 签名使用 `PyJWT` (HS256)；
> `/api/auth` 开放 `/register`、`/login`，受保护端点 `/me` 与 `get_current_user` 依赖；
> 业务 API（chat/plugins/registry/admin_llm）注入当前用户鉴权与角色拦截；
> 前端 `web/app/auth` 登录/注册页就绪，`client.ts` 自动附带 Bearer Header；
> 单测新增 `test_auth_service.py` 与 `test_auth_api.py`，全套测试、ruff、mypy 与 next build 均通过。


### M2 · skill/tool 注册表(P0,第一特色)
| ID | 任务 | 依赖 |
|----|------|------|
| T2.1 | `skill_tools` 表迁移 | T0.4 |
| T2.2 | 注册表服务(查询/版本/依赖解析) | T2.1 |
| T2.3 | 平台内置资源:PDF 解析 tool、摘要 skill、结构化输出 skill | T2.2 |
| T2.4 | 注册表查询 API(`/registry/*`) | T2.2 |

> **M2 状态:已完成(2026-08-13)**。`skill_tools` 表主键为 `(id, version)` 复合主键
> (支持多版本,004 已同步);版本约束自研 semver 子集(`^`/`~`/精确/`>=`,不引入 packaging,
> 因 packaging 不支持 npm caret)。内置资源自描述(`builtin/` 各模块 RESOURCE + 实现),
> 数据迁移 `98efc5a8b1f9` 登记(单一来源)。`/api/registry/*` 只读三个接口,错误统一
> `{error:{code,message}}`(005 §1,main.py 异常处理)。注册表服务测试用真实 PG 测试库
> (`agentplatform_test`,conftest 共享,PG 不可达自动 skip)。`pdf_parse` 实现留 M5
> 执行器接入时引入 pypdf。

### M3 · LLM 网关(P0)
| ID | 任务 | 依赖 |
|----|------|------|
| T3.1 | `llm_endpoints` 表迁移 + 管理 API(`/admin/llm-endpoints`) | T0.4 |
| T3.2 | OpenAI 兼容客户端(流式转发) | T3.1 |
| T3.3 | 模型路由(助手指定单一模型) | T3.2 |

> **M3 状态:已完成(2026-08-13)**。`llm_endpoints` 表与 004 一致;api_key 用 Fernet
> 加密存储(密钥由 SECRET_KEY 派生,`core/llm/crypto.py`),明文不落库/不回传。
> 客户端 `core/llm/client.py` 用 httpx 实现 chat/completions SSE 流式,支持 tools
> (供 M5 显式调用);`core/llm/router.py` 按 model 精确匹配、`is_default` 兜底。
> 测试 73 passed(ruff/mypy 全绿);已用 codingplan 端点(`deepseek-v4-flash`,
> `ark.cn-beijing.volces.com/api/coding/v3`)真实冒烟通过。

### M4 · 插件管理(P0)
| ID | 任务 | 依赖 |
|----|------|------|
| T4.1 | `plugins` 表迁移 | T0.4 |
| T4.2 | 插件加载器(进程内动态加载 + 清单校验 + 依赖解析) | T4.1, T2.2 |
| T4.3 | 插件部署 API(`/plugins/deploy`,接收 CLI 上传) | T4.2 |
| T4.4 | 插件管理 API(列表/启停/卸载) | T4.2 |

> **M4 状态:已完成(2026-08-13)**。`plugins` 表与 004 一致(manifest jsonb、status
> active/disabled,唯一约束 name+version)。加载器 `core/plugin/loader.py` 校验清单 →
> 复用 M2 注册表解析 depends_on → 登记插件 → 登记自有 skill/tool(source=private,
> owner=插件名,便于卸载清理)。`/api/plugins` 部署/列表/启停/卸载(005 §5),错误
> 统一 422 `{error:{code,message}}`(dependency_missing / plugin_invalid)。
> 清单以结构化 JSON 接收(YAML 解析在 M9 CLI 引入 PyYAML)。测试 90 passed。
> 示例插件:`docs/examples/plugins/prd-review-assistant/`(依赖内置 pdf_parse +
> summarize),已用真实 API 部署验证(注册、依赖校验 422 均通过)。skill/tool
> 代码加载与执行留 M5。

### M5 · agent 运行时(P0,核心)
| ID | 任务 | 依赖 |
|----|------|------|
| T5.1 | tool 执行器 + skill 执行器(简单 skill:prompt 模板+参数) | T2.2, T4.2 |
| T5.2 | 显式调用编排:依赖 skill/tool 映射为 LLM `tools` + 执行 + 回填 | T5.1, T3.2 |
| T5.3 | 上下文/会话管理(组装系统提示、历史、Redis 缓存) | T0.3 |
| T5.4 | agent 调度循环(LLM -> tool_call -> 回填 -> 再推理) | T5.2, T5.3 |

> **M5 状态:已完成(2026-08-13)**。`core/agent/`:executor(按 impl_path 解析实现;
> tool 调 `run(**args)`,简单 skill 调 `build_prompt(**args)` 后嵌套一次 LLM 调用
> 002 §5.3;插件相对路径代码未加载时报 AgentExecError,代码上传在 M9)、
> tools(注册表行 -> OpenAI function 定义,002 §5.1 映射)、messages(系统提示
> 列出可调用资源 + [system,history,user] 组装;Redis 缓存留 M6)、loop(LLM ->
> tool_call -> 执行 -> 回填 -> 再推理,执行失败回填文本让 LLM 自纠,输出
> ToolTrace 供 M6 SSE)。llm_client 注入可 mock;测试 101 passed(ruff/mypy 全绿)。
> 已用 codingplan(deepseek-v4-flash)真实跑通完整显式调用循环:
> 模型显式调用 skill:summarize -> 嵌套 LLM 产出摘要 -> 回填 -> 最终回答。

### M6 · 对话 API 与流式(P0)
| ID | 任务 | 依赖 |
|----|------|------|
| T6.1 | `sessions` / `messages` 表迁移 | T0.4 |
| T6.2 | 对话 API(创建会话、发消息、SSE 流) | T6.1, T5.4 |
| T6.3 | SSE 事件:`token` / `tool_call` / `component` / `done` / `error` | T6.2 |

> **M6 状态:已完成(2026-08-14)**。`sessions`/`messages` 表与 004 一致(messages.blocks
> 存 ContentBlock 信封,content 仅历史兼容);对话编排 `core/chat/`(插件 -> LLM 端点
> 解析 -> stream_agent 流式循环);`/api/chat` 建会话/发消息(SSE)/列表/历史(005 §4)。
> SSE 事件:delta{block_index,text} / tool_call{kind,name,args,result} / done{message_id}
> / error{code,message}(block_meta 等富交互事件留 M7)。M5 loop 增加流式 `stream_agent`
> (run_agent 聚合兼容)。流结束落库 assistant 最终消息;`build_history` 从 blocks 提取
> 文本。测试 107 passed(ruff/mypy 全绿)。**修复 M3 遗留 bug**:admin_llm POST/PATCH 缺
> commit(同会话可见但新会话查不到),已补 commit + 回归测试。已用 codingplan 真实跑通
> 完整对话流:模型显式调用 skill:summarize -> 嵌套摘要 -> delta 流式 -> done 落库。

### M7 · 富交互组件(P1)
| ID | 任务 | 依赖 |
|----|------|------|
| T7.1 | `interact_events` 表迁移与 ORM 模型 | T0.4 |
| T7.2 | `output_block` 工具拦截机制与 `block_meta` SSE 下发 | T5.2, T6.2 |
| T7.3 | 交互回传 API (`/chat/sessions/{sid}/blocks/{bid}/interact`) + 反馈事件 API | T7.2, T6.2 |
| T7.4 | 前端 22 种 Renderer (8 种展示类 + 11 种交互输入类 + 3 种反馈动作类) | T0.2 |
| T7.5 | 前端 Registry 调度中心 + 深度限制 (<=3) 与 Fallback 优雅降级 | T7.4 |

> **M7 状态:已完成(2026-08-15)**。
> 数据库迁移 `a8e411bf9812_add_interact_events_table.py`（记录 interact / thumbs / regenerate 审计事件）；
> 后端引入 `output_block` 工具拦截并支持流式推送 `block_meta` SSE 事件；
> 后端提供 `/chat/sessions/{sid}/blocks/{bid}/interact` 交互回传与 `/events` 轻反馈端点；
> 前端 `RendererRegistry` 统一注册 22 种内置组件（Markdown/Code/Table/Card/Collapsible/Image/File/Mermaid 与 Form/Confirm/Select 等输入控件）；
> 前端 `BlockRenderer` 严格限制嵌套深度 <= 3 并在异常/超深/未知类型时自动降级到 `FallbackRenderer`；
> 单测与质量检查全绿。

### M8 · 前端 WebUI
| ID | 任务 | 依赖 | 优先级 |
|----|------|------|--------|
| T8.1 | 对话页(消息流、流式渲染、组件渲染) | T6.3, T7.4 | P0 |
| T8.2 | 助手列表页(浏览/搜索/选用) | T4.4 | P1 |
| T8.3 | 会话历史与管理抽屉(切换/重命名/删除) | T6.2 | P1 |
| T8.4 | 开发者管理台(插件启停/卸载/LLM端点) | T4.4 | P1 |

> **M8 状态:已完成(2026-08-15)**。
> 全局导航栏 `Navbar` 整合「对话工作台」、「助手广场」、「开发者中心」与用户鉴权状态；
> **T8.1/T8.3**：对话页集成左侧折叠式 `SessionDrawer`（支持新建、切换、行内重命名、删除会话），消息列表完美渲染 ContentBlock 与流式 SSE；
> **T8.2 助手广场**：`/assistants` 页面支持按名称与描述实时搜索、卡片化展示版本/作者/模型/依赖标签，一键「开始对话」自动创建助手会话并跳转；
> **T8.4 开发者中心**：`/developer` 页面提供插件管理（查看清单、启停、卸载）与 OpenAI 兼容 LLM 端点管理（添加端点、设置默认模型）；
> `npm run build` 全量静态生成（7 页面）完全通过。


### M9 · 插件 SDK 与 CLI(P0,AI-native)
| ID | 任务 | 依赖 |
|----|------|------|
| T9.1 | `agentplatform.sdk` 包(`@skill`/`@tool` 装饰器、基类、schema 工具) | T2.2, T5.1 |
| T9.2 | CLI `init` / `validate`(结构化输出) | T9.1 |
| T9.3 | CLI `dev`(本地运行调试,不依赖远程平台) | T9.1, T5.4 |
| T9.4 | CLI `deploy`(部署协议,对接 `/plugins/deploy`) | T4.3, T9.1 |
| T9.5 | CLI `logs` / `test` | T9.4 |
| T9.6 | 插件开发规范文档(可作 Claude Code skill 加载) | T9.1 |

### M10 · 集成与示例(P2)
| ID | 任务 | 依赖 |
|----|------|------|
| T10.1 | 端到端联调(CLI 开发部署 -> 平台加载 -> 助手市场 -> 对话 -> 交互回传) | M9, M6, T8.1 |
| T10.2 | 示例插件:PRD 评审助手(验证 SDK 装饰器 + skill/tool 复用 + 富交互) | T10.1, T7 |
| T10.3 | 部署与使用文档 (README / deployment.md / plugin_development_guide.md) | T10.1 |

> **M10 状态:已完成(2026-08-15)**。
> **T10.2 示例插件**：`docs/examples/plugins/prd-review-assistant/` 完整落地（依赖平台内置 `pdf_parse` + `summarize`，自有 `skill:prd_review` 与确定性打分 `tool:prd_score`，配套 `test/test_review.yaml` 测试用例）；`agentplatform validate` 校验 100% 通过；
> **T10.1 E2E 联调**：`agentplatform/tests/test_e2e_integration.py` 自动化测试全链路（注册登录 ➔ 插件部署 ➔ 助手广场检索 ➔ 会话流式对话 ➔ 交互回传 ➔ 插件卸载）；
> **T10.3 文档体系**：项目根目录 `README.md`、`docs/deployment.md`（生产部署指南）与 `docs/plugin_development_guide.md`（AI 原生插件开发者手册）全部完备。


## 4. 建议实施顺序(拓扑序 + 优先级)

**Phase 1 · 核心链路跑通(P0):**
```
M0 脚手架 -> M2 注册表(+内置资源)-> M3 LLM 网关 -> M4 插件加载
-> M5 agent 运行时 -> M6 对话 API+SSE -> T8.1 对话页
-> M9 SDK+CLI -> T10.1 端到端联调
```
目标:能用 CLI 开发部署插件,前端能对话,显式调用 skill/tool 跑通。

**Phase 2 · MVP 完善(P1):**
```
M1 认证 -> M7 富交互组件 -> T8.2 助手列表 / T8.3 历史 / T8.4 管理台
```

**Phase 3 · 验证与打磨(P2):**
```
T10.2 示例插件(PRD 评审)-> T10.3 文档
```

## 5. 说明
- 核心链路先**不接认证**(T1.x 后置),用最快速度打通"开发-部署-对话"
- 富交互(M7)在纯文本对话跑通后再加,降低初期复杂度
- 示例插件(PRD 评审)作为第一特色的验证场景,放在最后做透
