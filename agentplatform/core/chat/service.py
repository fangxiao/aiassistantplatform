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
    """插件可调用的资源 id:depends_on(取 id 部分)+ 自有 skills/tools。

    去重保序:可选依赖(T11.10,dep 以 '?' 结尾)与插件本地同名回退实现
    指向同一 id,resolve() 按"公共优先、私有回退"选出实际执行版本。
    """
    m = plugin.manifest or {}
    ids = [split_dependency(d)[0] for d in m.get("depends_on", [])]
    for section in ("skills", "tools"):
        for r in m.get(section, []):
            ids.append(r["id"])
    return list(dict.fromkeys(ids))


async def make_llm_client(
    session: AsyncSession, model: str | None, user_id: str | None = None
) -> OpenAIClient:
    """按模型解析端点并构造客户端(用户自定义端点优先);无可用端点回退到 .env,均无抛 ChatError。"""
    fallbacks: list[LlmEndpoint] = []
    from agentplatform.config import settings
    from agentplatform.core.llm import crypto
    from agentplatform.core.llm.model import LlmEndpoint

    endpoint = None
    # 指定了模型:DB 精确匹配优先(用户自定义 > 平台共享)——用户自定义模型生效的前提;
    # env 默认端点只做兜底,不再无条件抢占
    if model:
        endpoint = await resolve_endpoint(session, model, user_id=user_id)
    if endpoint is None and settings.openai_base_url and settings.openai_api_key:
        endpoint = LlmEndpoint(
            name="default_env",
            base_url=settings.openai_base_url,
            model=model or settings.default_model,
            api_key_enc=crypto.encrypt(settings.openai_api_key),
            is_default=True,
        )
    if endpoint is None:
        endpoint = await resolve_endpoint(session, model or "", user_id=user_id)
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
        same_base = endpoint.base_url.rstrip("/") == settings.fallback_openai_base_url.rstrip("/")
        # 兜底条件:不同网关,或同网关但模型不同——后者覆盖"单模型上游故障"
        # (2026-09-26 glm-5.3-flash 上游 502 反复出现,同网关换模型即可续跑)
        if not same_base or endpoint.model != settings.fallback_default_model:
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
    images: list[str] | None = None,
    save_input: bool = True,
    docs: list[str] | None = None,
) -> AsyncIterator[AgentEvent]:
    """为一次发消息构建 agent 流(供 API SSE 消费)。

    流程:保存用户消息 -> 解析插件资源 -> 解析 LLM 端点 -> stream_agent。
    """
    sess = await get_session(session, session_id)
    if sess is None:
        raise ChatError("会话不存在")
    # 打磨⑥:单文档即问——拉取文档正文(pdf 解析/md·txt 直读),注入 prompt
    doc_context = await _load_doc_context(docs) if docs else ""
    if save_input:
        await save_user_message(
            session, session_id, user_message, images=images, docs=docs
        )

    plugin = await get_plugin(session, sess.plugin_id) if sess.plugin_id else None
    manifest = (plugin.manifest or {}) if plugin else None
    model = (manifest or {}).get("model")
    # 多模态路由(设计 012):含图消息切换到多模态模型——不支持视觉的模型传图直接报错
    if images:
        from agentplatform.config import settings as _settings

        if _settings.multimodal_model:
            model = _settings.multimodal_model
    resource_ids = resource_ids_from_plugin(plugin) if plugin else []
    client = await make_llm_client(session, model, user_id=sess.user_id)
    # 知识库检索允许范围(设计 008 §3.3/§4.3):会话挂载 ∪ 插件静态依赖 ∪ 助手挂载,唯一授权来源
    plugin_mounted = [
        uuid.UUID(k) for k in (getattr(plugin, "mounted_kb_ids", None) or [])
    ] if plugin else []
    allowed_kb_ids = await resolve_allowed_kb_ids(
        session,
        mounted_kb_ids=[uuid.UUID(k) for k in (sess.mounted_kb_ids or [])],
        plugin_manifest=manifest,
        plugin_mounted_kb_ids=plugin_mounted,
    )
    # 挂载了知识库则下发显式检索工具(builtin tool:kb_search,设计 008 §4.1)
    if allowed_kb_ids and KB_SEARCH_TOOL_ID not in resource_ids:
        resource_ids = [*resource_ids, KB_SEARCH_TOOL_ID]
    # 个人待办工具无条件注入(M14 AI 联动):平台级个人能力,不要求助手声明依赖
    from agentplatform.core.workbench.todo_tool import WORKBENCH_TODO_TOOL_ID
    from agentplatform.core.memory.tool import MEMORY_TOOL_ID
    from agentplatform.core.agent.http_action import HTTP_ACTION_TOOL_ID
    from agentplatform.core.agent.web_search import WEB_SEARCH_TOOL_ID

    if WORKBENCH_TODO_TOOL_ID not in resource_ids:
        resource_ids = [*resource_ids, WORKBENCH_TODO_TOOL_ID]
    if MEMORY_TOOL_ID not in resource_ids:
        resource_ids = [*resource_ids, MEMORY_TOOL_ID]
    if WEB_SEARCH_TOOL_ID not in resource_ids:
        resource_ids = [*resource_ids, WEB_SEARCH_TOOL_ID]
    if HTTP_ACTION_TOOL_ID not in resource_ids:
        resource_ids = [*resource_ids, HTTP_ACTION_TOOL_ID]

    # 用户长期记忆注入(M15 P1):有记忆才传,助手"记得"用户
    from agentplatform.core.memory import service as memory_service

    memories = await memory_service.memories_for_prompt(session, str(sess.user_id)) if sess.user_id else []
    history = await build_history(session, session_id)
    # history 末尾是刚保存的用户消息,拆出作为 user_message,其余作为前文
    if history:
        prior = history[:-1]
    else:
        prior = []
    effective_message = (
        f"{doc_context}\n\n---\n\n用户问题: {user_message}" if doc_context else user_message
    )
    async for ev in stream_agent(
        session,
        client,
        resource_ids=resource_ids,
        user_message=effective_message,
        history=prior,
        owner_id=str(sess.user_id) if sess.user_id else None,
        plugin_desc=(plugin.manifest or {}).get("description") if plugin else None,
        allowed_kb_ids=allowed_kb_ids,
        memories=memories,
        images=images,
    ):
        yield ev


_MAX_DOC_CONTEXT_CHARS = 30000  # 即问文档截断;更大请引导用户入知识库


async def _load_doc_context(docs: list[str] | None) -> str:
    """拉取即问文档正文:服务端 /api/files/raw URL → 本地路径解析。"""
    if not docs:
        return ""
    from pathlib import Path
    from urllib.parse import parse_qs, urlparse

    from agentplatform.core.kb.pipeline import parse_document

    parts: list[str] = []
    for url in docs[:2]:
        try:
            local = Path(parse_qs(urlparse(url).query).get("path", [""])[0])
            if not local.exists() or not local.is_file():
                continue
            suffix = local.suffix.lower()
            mime = (
                "application/pdf" if suffix == ".pdf"
                else "text/markdown" if suffix in (".md", ".markdown")
                else "text/plain"
            )
            text = parse_document(mime, local)
            if text and text.strip():
                name = local.name
                parts.append(f"【文档 {name}】\n{text.strip()[:_MAX_DOC_CONTEXT_CHARS]}")
        except Exception:  # noqa: BLE001  单文档失败跳过,不阻塞对话
            continue
    return "\n\n".join(parts)
