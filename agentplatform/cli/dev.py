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
        _attach_dev_impls(root)
        # 本地端点直接构造客户端(dev 模式不经 DB 查端点)
        client = OpenAIClient(endpoint)
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



def _attach_dev_impls(root: Path) -> None:
    """把插件代码中加载到的 @tool / @skill 实现函数注册到执行器的内存注册表中。"""
    from agentplatform.cli.yaml_io import load_manifest
    from agentplatform.core.agent.executor import clear_dev_registry, register_dev_impl
    from agentplatform.sdk.loader import load_resources

    clear_dev_registry()
    manifest_path = root / "plugin.yaml"
    if not manifest_path.exists():
        return
    try:
        raw = load_manifest(manifest_path)
    except Exception:  # noqa: BLE001
        return

    for section in ("skills", "tools"):
        for res in raw.get(section, []) or []:
            f = root / res.get("file", "")
            if f.exists():
                try:
                    for r in load_resources(str(f)):
                        if "impl" in r:
                            register_dev_impl(r["id"], r["impl"])
                except Exception as exc:  # noqa: BLE001
                    print(f"警告: 加载插件实现失败 ({res.get('file')}): {exc}")
