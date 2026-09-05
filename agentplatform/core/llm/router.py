"""模型路由(设计 003「助手指定单一模型」/ 001 §LLM 网关)。

助手/插件声明单一模型名(如 glm-5.2);按 model 精确匹配端点,
无匹配时回退到 is_default 端点。
"""

import itertools
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.llm.model import LlmEndpoint

_model_cycler: Iterator[str] | None = None


def get_next_model(
    model: str | None = None,
    *,
    is_multimodal: bool = False,
    available_models: list[str] | None = None,
) -> str:
    """获取目标模型名。支持显式指定、多模态优选及多可用模型轮询 (Round-Robin)。"""
    from agentplatform.config import settings

    if is_multimodal:
        return getattr(settings, "multimodal_model", "gemma-4-31b")

    if model and model.lower() not in ("auto", "round_robin", "default", ""):
        return model

    models = available_models or getattr(settings, "model_list", None)
    if not models:
        return getattr(settings, "default_model", "gpt-oss-120b")

    global _model_cycler
    if _model_cycler is None:
        _model_cycler = itertools.cycle(models)

    return next(_model_cycler)


def get_multimodal_model() -> str:
    """获取平台推荐的多模态/生图兼容大模型。"""
    from agentplatform.config import settings

    return getattr(settings, "multimodal_model", "gemma-4-31b")


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


