"""CLI 本地对话执行器 (供 Claude Code / 脚本在人肉测试模式下静默调用并输出纯净助手回复)。"""

from __future__ import annotations

import json
from pathlib import Path

from agentplatform.cli.dev import _attach_dev_impls
from agentplatform.cli.validate import validate_project
from agentplatform.config import settings
from agentplatform.core.agent.loop import run_agent
from agentplatform.core.llm import crypto
from agentplatform.core.llm.client import OpenAIClient
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
        except Exception:
            history = []

    val_res = validate_project(root)
    if not val_res["ok"]:
        return f"插件校验失败: {val_res['errors']}"

    base_url = base_url or settings.openai_base_url or "https://api.eaglesine.com/v1"
    api_key = api_key or settings.openai_api_key or "dev"
    model = model or settings.default_model or "DeepSeek-V3"

    endpoint = LlmEndpoint(
        name="dev_chat",
        base_url=base_url,
        model=model,
        api_key_enc=crypto.encrypt(api_key),
        is_default=True,
    )
    client = OpenAIClient(endpoint)
    _attach_dev_impls(root)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        from agentplatform.cli import yaml_io
        from agentplatform.core.registry.service import seed_builtin, split_dependency

        # 注册平台内置/公共技能与工具
        await seed_builtin(session)

        for r in val_res["resources"]:
            await register(
                session,
                resource_id=r["id"],
                kind=SkillToolKind(r["kind"]),
                name=r["id"].split(":", 1)[1],
                version=r["version"],
                source=SkillToolSource.private,
                schema_=r["schema"],
                impl_path=r.get("file", ""),
                owner_id="dev",
            )

        manifest_path = root / "plugin.yaml"
        raw_m = yaml_io.load_manifest(manifest_path) if manifest_path.exists() else {}
        dep_ids = [split_dependency(d)[0] for d in raw_m.get("depends_on", []) or []]
        resource_ids = list(dict.fromkeys(dep_ids + [r["id"] for r in val_res["resources"]]))

        result = await run_agent(
            session,
            client,
            resource_ids=resource_ids,
            user_message=message,
            history=history,
        )

    # 更新并保存历史
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": result.text})
    try:
        history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    return result.text
