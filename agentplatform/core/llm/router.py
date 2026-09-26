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


def normalize_model(model: str | None) -> str:
    """模型名归一:auto 透传网关(网关侧自行路由);空值回平台默认模型。

    2026-09-26 决策修订:曾一度把 auto 收口为平台默认强模型(网关抽签质量不可控);
    用户裁决改回**网关 auto 透传**——路由智能归网关,弱模型排除通过与网关沟通
    在其 auto 池配置黑名单解决(平台侧黑名单无法感知网关实际池构成)。
    """
    from agentplatform.config import settings

    if not model:
        return settings.default_model
    return model


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
    session: AsyncSession, model: str, user_id: str | None = None
) -> LlmEndpoint | None:
    """按模型名解析端点:用户自定义优先于平台共享;无精确匹配回退默认。

    优先级:用户精确匹配 > 共享精确匹配 > 用户默认 > 共享默认 > None。
    model 中的 auto/round_robin/default 先收口为平台默认模型(见 normalize_model)。
    """
    model = normalize_model(model)
    rows = list(
        await session.scalars(select(LlmEndpoint).order_by(LlmEndpoint.is_default.desc()))
    )
    own = [ep for ep in rows if user_id is not None and ep.owner_id == str(user_id)]
    shared = [ep for ep in rows if ep.owner_id is None]
    for ep in own:
        if ep.model == model:
            return ep
    for ep in shared:
        if ep.model == model:
            return ep
    for ep in own:
        if ep.is_default:
            return ep
    for ep in shared:
        if ep.is_default:
            return ep
    return None


