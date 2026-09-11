"""对话编排(设计 005 §4 / 003 v2.0 §3)。

把「插件 -> LLM 端点/客户端 -> agent 流式循环」串起来;历史组装。
"""

import uuid
from collections.abc import AsyncIterator

from agentplatform.core.agent.loop import AgentEvent, stream_agent
from agentplatform.core.kb.search_tool import KB_SEARCH_TOOL_ID, resolve_allowed_kb_ids
from agentplatform.core.llm.client import OpenAIClient
from agentplatform.core.llm.router import resolve_endpoint
from agentplatform.core.message.service import build_history, save_user_message
from agentplatform.core.plugin.loader import get_plugin
from agentplatform.core.plugin.model import Plugin
from agentplatform.core.registry.service import split_dependency
from agentplatform.core.session.service import get_session
from sqlalchemy.ext.asyncio import AsyncSession


class ChatError(Exception):
    """对话错误。"""


def resource_ids_from_plugin(plugin: Plugin) -> list[str]:
    """插件可调用的资源 id:depends_on(取 id 部分)+ 自有 skills/tools。"""
    m = plugin.manifest or {}
    ids = [split_dependency(d)[0] for d in m.get("depends_on", [])]
    for section in ("skills", "tools"):
        for r in m.get(section, []):
            ids.append(r["id"])
    return ids


async def make_llm_client(session: AsyncSession, model: str | None) -> OpenAIClient:
    """按模型解析端点并构造客户端;无可用端点回退到 .env 配置，均无抛 ChatError。"""
    fallbacks: list[LlmEndpoint] = []
    from agentplatform.config import settings
    from agentplatform.core.llm import crypto
    from agentplatform.core.llm.model import LlmEndpoint

    if settings.openai_base_url and settings.openai_api_key:
        endpoint = LlmEndpoint(
            name="default_env",
            base_url=settings.openai_base_url,
            model=model or settings.default_model,
            api_key_enc=crypto.encrypt(settings.openai_api_key),
            is_default=True,
        )
    else:
        endpoint = await resolve_endpoint(session, model or "")
        if endpoint is None:
            if settings.fallback_openai_base_url and settings.fallback_openai_api_key:
                endpoint = LlmEndpoint(
                    name="fallback_env_primary",
                    base_url=settings.fallback_openai_base_url,
                    model=settings.fallback_default_model,
                    api_key_enc=crypto.encrypt(settings.fallback_openai_api_key),
                    is_default=True,
                )
            else:
                raise ChatError(f"未配置可用 LLM 端点(模型: {model or '默认'})")

    if settings.fallback_openai_base_url and settings.fallback_openai_api_key:
        if endpoint.base_url.rstrip("/") != settings.fallback_openai_base_url.rstrip("/"):
            fallbacks.append(
                LlmEndpoint(
                    name="fallback_env",
                    base_url=settings.fallback_openai_base_url,
                    model=settings.fallback_default_model,
                    api_key_enc=crypto.encrypt(settings.fallback_openai_api_key),
                    is_default=False,
                )
            )

    return OpenAIClient(endpoint, fallback_endpoints=fallbacks)



async def agent_stream_for_session(
    session: AsyncSession,
    session_id: uuid.UUID,
    user_message: str,
) -> AsyncIterator[AgentEvent]:
    """为一次发消息构建 agent 流(供 API SSE 消费)。

    流程:保存用户消息 -> 解析插件资源 -> 解析 LLM 端点 -> stream_agent。
    """
    sess = await get_session(session, session_id)
    if sess is None:
        raise ChatError("会话不存在")
    await save_user_message(session, session_id, user_message)

    plugin = await get_plugin(session, sess.plugin_id) if sess.plugin_id else None
    manifest = (plugin.manifest or {}) if plugin else None
    model = (manifest or {}).get("model")
    resource_ids = resource_ids_from_plugin(plugin) if plugin else []
    client = await make_llm_client(session, model)
    # 知识库检索允许范围(设计 008 §3.3):挂载 ∪ 插件依赖,唯一授权来源
    allowed_kb_ids = await resolve_allowed_kb_ids(
        session,
        mounted_kb_ids=[uuid.UUID(k) for k in (sess.mounted_kb_ids or [])],
        plugin_manifest=manifest,
    )
    # 挂载了知识库则下发显式检索工具(builtin tool:kb_search,设计 008 §4.1)
    if allowed_kb_ids and KB_SEARCH_TOOL_ID not in resource_ids:
        resource_ids = [*resource_ids, KB_SEARCH_TOOL_ID]

    history = await build_history(session, session_id)
    # history 末尾是刚保存的用户消息,拆出作为 user_message,其余作为前文
    if history:
        prior = history[:-1]
    else:
        prior = []
    async for ev in stream_agent(
        session,
        client,
        resource_ids=resource_ids,
        user_message=user_message,
        history=prior,
        owner_id=str(sess.user_id) if sess.user_id else None,
        plugin_desc=(plugin.manifest or {}).get("description") if plugin else None,
        allowed_kb_ids=allowed_kb_ids,
    ):
        yield ev
