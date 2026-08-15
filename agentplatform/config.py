"""应用配置。

从环境变量 / .env 加载(见 .env.example)。LLM 端点等后续里程碑在此扩展。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = (
        "postgresql+asyncpg://agentplatform:agentplatform@localhost:5432/agentplatform"
    )
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-change-me"  # TODO(M1): 认证启用前必须改为环境变量注入
    # 全局 LLM 端点(开发/测试共用，由 .env 覆盖注入)
    openai_base_url: str = "https://api.eaglesine.com/v1"
    openai_api_key: str = ""
    default_model: str = "DeepSeek-V3"
    # 前端跨域来源(MVP dev:Next.js 3000;生产按环境注入)
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


settings = Settings()

