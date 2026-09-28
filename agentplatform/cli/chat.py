"""CLI 本地对话执行器 (供 Claude Code / 脚本在人肉测试模式下静默调用并输出纯净助手回复)。"""

from __future__ import annotations

import json
import uuid
from contextlib import suppress
from pathlib import Path

from agentplatform.cli.dev import _attach_dev_impls
from agentplatform.cli.validate import validate_project
from agentplatform.config import settings
from agentplatform.core.agent.loop import run_agent
from agentplatform.core.llm import crypto
from agentplatform.core.llm.client import OpenAIClient
from agentplatform.core.llm.router import normalize_model
from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.registry.model import SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import register

HISTORY_FILE = ".chat_history.json"


async def run_single_chat(
    root: Path,
    message: str,
    reset: bool = False,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """执行单轮本地对话并自动持久化多轮历史。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from agentplatform.core.db.engine import engine

    history_path = root / HISTORY_FILE
    if reset and history_path.exists():
        history_path.unlink()
        if not message:
            return "会话历史已重置。"

    history: list[dict] = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            history = []

    val_res = validate_project(root)
    if not val_res["ok"]:
        return f"插件校验失败: {val_res['errors']}"

    import os
    from agentplatform.cli import yaml_io
    from agentplatform.core.plugin.env import setup_plugin_env

    setup_plugin_env(root)

    manifest_path = root / "plugin.yaml"
    raw_m = yaml_io.load_manifest(manifest_path) if manifest_path.exists() else {}

    base_url = (
        base_url
        or os.environ.get("OPENAI_BASE_URL")
        or settings.openai_base_url
        or "https://api.ailearning.top/v1"
    )
    api_key = api_key or os.environ.get("OPENAI_API_KEY") or settings.openai_api_key or "dev"
    model = (
        model
        or os.environ.get("MODEL")
        or raw_m.get("model")
        or settings.default_model
        or "auto"
    )

    endpoint = LlmEndpoint(
        name="dev_chat",
        base_url=base_url,
        model=normalize_model(model),
        api_key_enc=crypto.encrypt(api_key),
        is_default=True,
    )

    fallbacks = []
    fb_base = getattr(settings, "fallback_openai_base_url", None)
    fb_key = getattr(settings, "fallback_openai_api_key", None)
    if fb_base and fb_key and fb_base.rstrip("/") != base_url.rstrip("/"):
        fb_model = getattr(settings, "fallback_default_model", "deepseek-v4-flash")
        fallbacks.append(
            LlmEndpoint(
                name="chat_fallback",
                base_url=fb_base,
                model=fb_model,
                api_key_enc=crypto.encrypt(fb_key),
                is_default=False,
            )
        )

    client = OpenAIClient(endpoint, fallback_endpoints=fallbacks)
    _attach_dev_impls(root)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        from agentplatform.core.registry.service import seed_builtin, split_dependency

        # 注册平台内置/公共技能与工具
        await seed_builtin(session)

        raw_skill_defs = {d.get("id"): d for d in (raw_m.get("skills") or []) if isinstance(d, dict)}
        for r in val_res["resources"]:
            schema = dict(r["schema"] or {})
            # T18.3:plugin.yaml 的 required_tools 合入本地注册行(与服务端 deploy 同语义,
            # 否则编排保障仅在服务端会话生效——writewx 20260928-1201 验收发现的覆盖缺口)
            rt = (raw_skill_defs.get(r["id"]) or {}).get("required_tools")
            if r["kind"] == "skill" and isinstance(rt, list) and rt:
                schema["required_tools"] = [str(x) for x in rt]
            await register(
                session,
                resource_id=r["id"],
                kind=SkillToolKind(r["kind"]),
                name=r["id"].split(":", 1)[1],
                version=r["version"],
                source=SkillToolSource.private,
                schema_=schema,
                impl_path=r.get("file", ""),
                description=r.get("description") or f"Resource {r['id']}",
                owner_id="dev",
            )

        dep_ids = [split_dependency(d)[0] for d in raw_m.get("depends_on", []) or []]
        resource_ids = list(dict.fromkeys(dep_ids + [r["id"] for r in val_res["resources"]]))

        # KB 检索范围(20260928-0959 修复):对齐服务端 chat 语义——本地 CLI
        # 此前不组装 allowed_kb_ids,kb_search 空范围必然零命中,风格学习
        # 等依赖知识库的能力在本地调试态静默失效(dev/prod 行为漂移)。
        allowed_kb: list = []
        try:
            from sqlalchemy import select as _select

            from agentplatform.core.plugin.model import Plugin

            prow = (
                await session.scalar(_select(Plugin).where(Plugin.name == raw_m.get("name")))
            )
            allowed_kb = [uuid.UUID(k) for k in (getattr(prow, "mounted_kb_ids", None) or [])]
        except Exception:  # noqa: BLE001  本地无该插件登记时不影响普通调试
            allowed_kb = []
        if allowed_kb:
            from agentplatform.core.kb.search_tool import KB_SEARCH_TOOL_ID

            if KB_SEARCH_TOOL_ID not in resource_ids:
                resource_ids = [*resource_ids, KB_SEARCH_TOOL_ID]

        result = await run_agent(
            session,
            client,
            resource_ids=resource_ids,
            user_message=message,
            history=history,
            allowed_kb_ids=allowed_kb or None,
        )

    # 更新并保存历史
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": result.text})
    with suppress(OSError):
        history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    return result.text
