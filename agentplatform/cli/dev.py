"""CLI dev(006 §6.1):本地对话调试,复用 M5 agent 循环 + OpenAI 兼容本地端点。

远程模式(设计 007):dev --target 上传插件到平台端执行 agent 循环,SSE 流回显。
"""

from __future__ import annotations

import json
from pathlib import Path

from agentplatform.cli.validate import validate_project
from agentplatform.core.agent.loop import stream_agent
from agentplatform.core.llm import crypto
from agentplatform.core.llm.client import OpenAIClient
from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.plugin.env import setup_plugin_env
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

    data_dir = setup_plugin_env(root, target_url=base_url)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        from agentplatform.cli import yaml_io
        from agentplatform.core.registry.service import seed_builtin, split_dependency

        # 注册平台内置/公共技能与工具
        await seed_builtin(session)

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
                description=r.get("description") or f"Resource {r['id']}",
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

        # 解析 depends_on 与自有资源 id 集合
        manifest_path = root / "plugin.yaml"
        raw_m = yaml_io.load_manifest(manifest_path) if manifest_path.exists() else {}
        dep_ids = [split_dependency(d)[0] for d in raw_m.get("depends_on", []) or []]
        all_resource_ids = list(dict.fromkeys(dep_ids + [r["id"] for r in result["resources"]]))

        fallbacks = []
        from agentplatform.config import settings
        fb_base = getattr(settings, "fallback_openai_base_url", None)
        fb_key = getattr(settings, "fallback_openai_api_key", None)
        if fb_base and fb_key and fb_base.rstrip("/") != base_url.rstrip("/"):
            fb_model = getattr(settings, "fallback_default_model", "deepseek-v4-flash")
            fallbacks.append(
                LlmEndpoint(
                    name="dev_fallback",
                    base_url=fb_base,
                    model=fb_model,
                    api_key_enc=crypto.encrypt(fb_key),
                    is_default=False,
                )
            )

        # 本地端点直接构造客户端(dev 模式不经 DB 查端点, 支持自动故障转移)
        client = OpenAIClient(endpoint, fallback_endpoints=fallbacks)
        print("=== 本地 dev 对话(输入 exit 退出)===")
        print(f"📦 已挂载资源 ({len(all_resource_ids)}): {', '.join(all_resource_ids)}")
        print(f"📁 插件数据目录: {data_dir}")
        while True:
            try:
                text = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in ("exit", "quit"):
                break
            async for ev in stream_agent(session, client, resource_ids=all_resource_ids, user_message=text):
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


# ---------------------------------------------------------------------------
# 远程调试模式 (设计 007 §4): dev --target 上传插件到平台端执行
# ---------------------------------------------------------------------------


def _load_dev_token(target: str) -> str | None:
    """解析远程调试令牌:AGENTPLATFORM_TOKEN 环境变量 > ~/.agentplatform/config.json > None。"""
    import os

    env_token = os.environ.get("AGENTPLATFORM_TOKEN")
    if env_token:
        return env_token

    user_cfg = Path.home() / ".agentplatform" / "config.json"
    if user_cfg.exists():
        try:
            cfg = json.loads(user_cfg.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("token"):
                return cfg["token"]
        except (OSError, ValueError):
            pass
    return None


def _build_dev_manifest(root: Path) -> dict:
    """读取 plugin.yaml 并给每个 skill/tool 注入源码 code(远程执行需要)。"""
    from agentplatform.cli.yaml_io import load_manifest

    manifest = load_manifest(root / "plugin.yaml")
    for section in ("skills", "tools"):
        for res in manifest.get(section, []) or []:
            if not isinstance(res, dict) or not res.get("file"):
                continue
            file_path = root / res["file"]
            if file_path.exists():
                res["code"] = file_path.read_text(encoding="utf-8")
    return manifest


def _print_dev_error(resp) -> None:
    """展示远程返回的结构化错误。"""
    try:
        body = resp.json()
        err = body.get("error", {})
        print(f"❌ 远程调试失败 ({resp.status_code}): {err.get('message', body)}")
    except Exception:  # noqa: BLE001
        print(f"❌ 远程调试失败 ({resp.status_code}): {resp.text[:200]}")


async def run_remote_dev_loop(root: Path, target: str) -> None:
    """远程 dev:上传插件 → 平台端执行 agent 循环 → SSE 流回显。

    不依赖本地数据库 / LLM 端点,运行时完全走远程平台。
    """
    import httpx

    # 1. 令牌解析
    token = _load_dev_token(target)
    if not token:
        print("❌ 未配置远程调试令牌。")
        print('请在环境变量设置: export AGENTPLATFORM_TOKEN="<jwt>"')
        print("或在 ~/.agentplatform/config.json 写入: {\"token\": \"<jwt>\"}")
        return
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 组装带源码的 manifest 并创建远程调试会话
    try:
        manifest = _build_dev_manifest(root)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 解析插件清单失败: {exc}")
        return

    base = target.rstrip("/")
    async with httpx.AsyncClient(timeout=30) as hclient:
        try:
            resp = await hclient.post(
                f"{base}/api/plugins/dev-session",
                json={"manifest": manifest},
                headers=headers,
            )
        except httpx.HTTPError as exc:
            print(f"❌ 连接远程平台失败: {exc}")
            return
        if resp.status_code != 201:
            _print_dev_error(resp)
            return

        session = resp.json()
        session_id = session["session_id"]
        resources = session.get("resources", [])
        data_dir = setup_plugin_env(root, target_url=target)
        print(f"🌐 远程调试模式: {base}")
        print(f"📦 已挂载资源 ({len(resources)}): {', '.join(resources)}")
        print(f"📁 插件数据目录: {data_dir}")
        print(f"💡 输入 exit 退出 (TTL {session.get('ttl_seconds', 1800)}s)")

        try:
            while True:
                try:
                    text = input("你> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if text.lower() in ("exit", "quit"):
                    break
                await _remote_chat_once(base, session_id, headers, text)
        finally:
            # 退出时主动清理远程会话
            try:
                resp = await hclient.delete(
                    f"{base}/api/plugins/dev-session/{session_id}", headers=headers
                )
                if resp.status_code in (200, 404):
                    print("✅ 远程调试会话已清理")
            except httpx.HTTPError:
                print("⚠️ 远程调试会话清理失败(将随 TTL 自动过期)")


async def _remote_chat_once(base: str, session_id: str, headers: dict, text: str) -> None:
    """发送一条调试消息,流式接收并打印 SSE 事件。"""
    import httpx

    async with httpx.AsyncClient() as client, client.stream(
        "POST",
        f"{base}/api/plugins/dev-session/{session_id}/messages",
        json={"content": text},
        headers=headers,
        timeout=120,
    ) as resp:
        if resp.status_code != 200:
            _print_dev_error(resp)
            return
        event_type = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if event_type == "delta":
                    print(data.get("text", ""), end="", flush=True)
                elif event_type == "tool_call":
                    name = data.get("name", "")
                    result = str(data.get("result", ""))[:60]
                    print(f"\n  ⚙ {name} -> {result}")
                elif event_type == "error":
                    print(f"\n  ❌ {data.get('message', '未知错误')}")
        print()
