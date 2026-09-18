"""应用配置。

从环境变量 / .env 加载(见 .env.example)。LLM 端点等后续里程碑在此扩展。
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_files() -> tuple[str, ...]:
    files = [
        str(Path.home() / ".agentplatform" / ".env"),
        str(Path.home() / ".config" / "agentplatform" / ".env"),
    ]
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        env_p = parent / ".env"
        if env_p.exists():
            files.append(str(env_p))
    return tuple(files)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_files(), env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = (
        "postgresql+asyncpg://agentplatform:agentplatform@localhost:5432/agentplatform"
    )
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-change-me"  # TODO(M1): 认证启用前必须改为环境变量注入
    # 默认主 LLM 端点 (个人智能网关 / 直连统一模型网关)
    openai_base_url: str = "https://api.ailearning.top/v1"
    openai_api_key: str = ""
    default_model: str = "auto"
    available_models: str = '["auto"]'
    multimodal_model: str = "auto"

    # 可选备用容灾 LLM 端点 (由 .env 决定是否启用)
    fallback_openai_base_url: str = ""
    fallback_openai_api_key: str = ""
    fallback_default_model: str = "auto"
    fallback_available_models: str = '["auto"]'

    @property
    def model_list(self) -> list[str]:
        import json
        v = (self.available_models or "").strip()
        if v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(m).strip() for m in parsed if str(m).strip()]
            except Exception:
                pass
        return [m.strip() for m in v.split(",") if m.strip()] or [self.default_model]
    # 前端跨域来源(MVP dev:Next.js 3000;生产按环境注入)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # 浏览器隧道(Browser Tunnel / T11.11)
    browser_tunnel_heartbeat: int = 30  # 服务端心跳探测间隔(秒)
    browser_tunnel_timeout: int = 15  # 心跳探测超时(秒),超时断开
    browser_route_timeout: int = 120  # 端侧动作最长等待(秒)
    # 本地联调用:允许任意登录用户的端侧动作路由到 dev token 注册的浏览器连接。
    # 生产环境必须保持 False——旧逻辑以 secret_key 是否为默认值推断,生产漏配密钥时
    # 会静默跨用户路由,属安全隐患,故改为显式开关。
    browser_dev_route_any: bool = False

    # 远程调试会话(Remote Dev / 设计 007)
    dev_session_ttl: int = 1800  # 调试会话 TTL(秒),默认 30 分钟
    dev_session_max_interactions: int = 100  # 每会话最大消息交互次数

    # 沙箱安全配置 (基于 @anthropic-ai/sandbox-runtime / srt)
    # 当前阶段默认关闭 (旁路模式)，待未来对外开放或托管不可信插件时一键开启
    sandbox_enabled: bool = False
    sandbox_runner_cmd: str = "srt"
    sandbox_high_risk_only: bool = True
    sandbox_timeout_seconds: int = 30

    # 知识库(M12,设计 008)
    kb_embedding_dim: int = 1024  # 与迁移中 vector 维度一致,变更需全量重算
    kb_embedding_model: str = ""  # 兜底 embedding 模型名;空则仅用端点表中 embedding 类型端点
    kb_max_document_mb: int = 20  # 单文档大小上限
    kb_max_documents_per_kb: int = 200  # 单库文档数上限
    kb_chunk_tokens: int = 512  # 切分目标长度
    kb_chunk_overlap_tokens: int = 50  # 切分重叠
    kb_search_top_k: int = 5  # kb_search 默认返回条数
    # 内容型连接器(M13,设计 009):网页抓取边界与调度节奏
    connector_fetch_timeout_s: int = 15  # 单页请求超时
    connector_max_page_bytes: int = 5 * 1024 * 1024  # 单页正文上限
    connector_max_pages: int = 200  # 单次同步页数上限(配置可调小,不可超此硬顶)
    connector_concurrency: int = 4  # 单源同步并发抓取数
    connector_user_agent: str = "AgentPlatformConnector/0.1 (+https://ailearning.top/bot)"
    connector_scheduler_tick_seconds: int = 60  # 调度器扫描间隔
    # 定时唤醒 agent(M15,设计 011)
    scheduler_tick_seconds: int = 60  # 任务调度扫描间隔
    scheduler_max_tasks_per_user: int = 10  # 每用户任务数上限
    scheduler_max_concurrent: int = 3  # 全局并发运行上限,超出顺延下个 tick
    scheduler_run_timeout_s: int = 600  # 单次运行超时(判失败)
    # 安全收敛(2026-09-17)
    file_serve_roots: list[str] = []  # /api/files 允许访问的额外根目录(绝对路径);默认仅 cwd 与 ~/.agentplatform
    allow_self_promote_developer: bool = False  # 注册接口是否允许自选 developer 角色(仅本地开发开)
    # 联网搜索(M15 P1):provider=tavily(需 WEB_SEARCH_API_KEY)/searxng(自托管,免费无限)
    web_search_api_key: str = ""
    web_search_provider: str = "tavily"
    searxng_base_url: str = "http://localhost:8888"
    memory_max_per_user: int = 50  # 每用户长期记忆条数上限(超出淘汰最旧)
    # 通用动作(M17):允许 agent 调用的域名白名单;空=工具禁用(安全默认)
    action_http_allowlist: list[str] = []
    action_require_confirm: bool = True  # 写操作(POST/PUT/PATCH/DELETE)须用户在确认框确认
    kb_shared_workspace_slug: str = "shared_workspace"  # 跨项目默认共享库(ADR 0006 前的共用约定,008 §11.3);置空禁用自动挂载


settings = Settings()


