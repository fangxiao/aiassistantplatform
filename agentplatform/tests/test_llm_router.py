"""模型路由测试(设计 003 助手指定单一模型)。"""

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.llm.router import resolve_endpoint
from agentplatform.core.llm.service import create_endpoint


async def _seed_endpoints(session: AsyncSession) -> None:
    await create_endpoint(session, name="glm", base_url="https://a", model="glm-5.2", api_key="k1")
    await create_endpoint(session, name="deepseek", base_url="https://b", model="deepseek-v4-flash", api_key="k2", is_default=True)
    await session.commit()


class TestResolveEndpoint:
    async def test_exact_model_match(self, session: AsyncSession) -> None:
        await _seed_endpoints(session)
        ep = await resolve_endpoint(session, "glm-5.2")
        assert ep is not None and ep.name == "glm"

    async def test_fallback_to_default(self, session: AsyncSession) -> None:
        await _seed_endpoints(session)
        ep = await resolve_endpoint(session, "unknown-model")
        assert ep is not None and ep.name == "deepseek"
        assert ep.is_default is True

    async def test_default_wins_over_other_model(self, session: AsyncSession) -> None:
        # 精确匹配优先于默认:即使存在默认端点,匹配到的模型端点胜出
        await _seed_endpoints(session)
        ep = await resolve_endpoint(session, "glm-5.2")
        assert ep is not None
        assert ep.name == "glm"

    async def test_none_when_empty(self, session: AsyncSession) -> None:
        assert await resolve_endpoint(session, "anything") is None
