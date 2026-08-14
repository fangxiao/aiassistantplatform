"""模型路由(设计 003「助手指定单一模型」/ 001 §LLM 网关)。

助手/插件声明单一模型名(如 glm-5.2);按 model 精确匹配端点,
无匹配时回退到 is_default 端点。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.llm.model import LlmEndpoint


async def resolve_endpoint(
    session: AsyncSession, model: str
) -> LlmEndpoint | None:
    """按模型名解析端点;无精确匹配回退默认端点;都无返回 None。"""
    rows = await session.scalars(
        select(LlmEndpoint).order_by(LlmEndpoint.is_default.desc())
    )
    default: LlmEndpoint | None = None
    for ep in rows:
        if ep.model == model:
            return ep
        if ep.is_default and default is None:
            default = ep
    return default
