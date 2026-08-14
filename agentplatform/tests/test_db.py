"""数据库基础冒烟测试(TDD:先写测试,再实现)。

M0 验收:配置可加载、Base 就绪、async engine 指向 asyncpg(不实际连库,
连接由 docker-compose 起的 pg 与迁移验证)。
"""

from agentplatform.config import settings
from agentplatform.core.db.base import Base
from agentplatform.core.db.engine import engine


def test_settings_database_url() -> None:
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_base_metadata_has_registry_table() -> None:
    # M2 起注册表表已登记;后续里程碑在此追加断言
    assert "skill_tools" in Base.metadata.tables


def test_engine_uses_asyncpg() -> None:
    assert engine.url.get_driver_name() == "asyncpg"
