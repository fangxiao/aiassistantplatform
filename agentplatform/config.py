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


settings = Settings()
