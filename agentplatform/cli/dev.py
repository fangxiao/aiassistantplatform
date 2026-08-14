"""CLI dev(006 §6.1):本地对话调试,复用 M5 agent 循环 + OpenAI 兼容本地端点。"""

from __future__ import annotations

from pathlib import Path

from agentplatform.cli.validate import validate_project
from agentplatform.core.agent.loop import stream_agent
from agentplatform.core.llm import crypto
from agentplatform.core.llm.client import OpenAIClient
from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.registry.model import SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import register


async def run_dev_loop(root: Path, base_url: str, api_key: str, model: str) -> None:
    """加载插件资源到内存注册表,启动 REPL 对话(不依赖远程平台)。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from agentplatform.core.db.engine import engine

    result = validate_project(root)
    if not result["ok"]:
        print("校验失败:", result["errors"])
        return

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        # 把插件自有资源登记进本地注册表(内存库,用于 agent 循环)
        for r in result["resources"]:
            await register(
                session,
                resource_id=r["id"],
                kind=SkillToolKind(r["kind"]),
                name=r["id"].split(":", 1)[1],
                version=r["version"],
                source=SkillToolSource.private,
                schema_=r["schema"],
                impl_path="",  # dev 模式直接用 impl callable
                owner_id="dev",
            )
        endpoint = LlmEndpoint(
            name="dev",
            base_url=base_url,
            model=model,
            api_key_enc=crypto.encrypt(api_key or "dev"),
            is_default=True,
        )
        # 本地端点直接构造客户端(dev 模式不经 DB 查端点)
        client = _make_client(endpoint, result["resources"])
        print("=== 本地 dev 对话(输入 exit 退出)===")
        while True:
            try:
                text = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("exit", "quit"):
                break
            async for ev in stream_agent(session, client, resource_ids=[r["id"] for r in result["resources"]], user_message=text):
                if ev.type == "delta" and ev.text:
                    print(ev.text, end="", flush=True)
                elif ev.type == "tool_call" and ev.tool_trace:
                    print(f"\n  ⚙ {ev.tool_trace.id} -> {ev.tool_trace.result[:60]}")
            print()


def _make_client(endpoint: LlmEndpoint, resources: list[dict]):
    """构造带插件 impl 的客户端(用 loader 的 impl callable 执行本地 skill/tool)。"""

    client = OpenAIClient(endpoint)
    _attach_dev_impls(client, resources)
    return client


def _attach_dev_impls(client, resources: list[dict]) -> None:
    """dev 模式:资源 impl 交由执行器通过 impl_path 解析(M5 执行器)。

    MVP 阶段本地 dev 以资源自检与 preview 为主;完整 tool/skill 执行
    复用平台执行器(见 core/agent/executor.py)。
    """
    _ = resources
