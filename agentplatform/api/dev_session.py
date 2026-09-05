"""远程调试会话 API（设计 007 §2 / §3）。

创建调试会话（上传 manifest + 源码 → 校验 → 注册临时资源 → 返回 session_id）、
SSE 对话流、清理、心跳。

错误统一为 {error: {code, message}}（005 §1），由 main.py 异常处理器落地。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.chat.sse import sse
from agentplatform.core.db.session import get_session
from agentplatform.core.plugin.dev_schemas import (
    DevSessionCreate,
    DevSessionMessageRequest,
    DevSessionOut,
)
from agentplatform.core.plugin.dev_session import DevSession, DevSessionError, dev_manager
from agentplatform.core.plugin.errors import PluginValidationError
from agentplatform.core.plugin.manifest import PluginManifest, validate_manifest
from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource
from agentplatform.core.registry.service import check_dependencies, register

router = APIRouter(prefix="/plugins/dev-session", tags=["dev-session"])


def _session_storage_dir(session_id: str) -> Path:
    """调试会话的临时代码存储目录。"""
    return Path.home() / ".agentplatform" / "dev_sessions" / session_id


async def _register_dev_resources(
    db: AsyncSession,
    manifest: PluginManifest,
    session_id: str,
    storage_dir: Path,
) -> list[str]:
    """把插件私有 skill/tool 代码写入临时目录并注册到注册表。返回资源 id 列表。"""
    from agentplatform.core.plugin.env import setup_plugin_env

    setup_plugin_env(plugin_name=manifest.name)

    resource_ids: list[str] = []
    for kind, section in (
        (SkillToolKind.skill, manifest.skills),
        (SkillToolKind.tool, manifest.tools),
    ):
        for res_def in section:
            # 1. 写入临时代码文件（复用 resolve_impl 的加载路径）
            file_path = storage_dir / res_def.file.lstrip("./")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(res_def.code or "", encoding="utf-8")

            # 2. 注册到注册表，owner_id 绑定会话便于清理
            await register(
                db,
                resource_id=res_def.id,
                kind=kind,
                name=res_def.id.split(":", 1)[1],
                version=manifest.version,
                source=SkillToolSource.private,
                schema_=res_def.schema_ or {"parameters": {"type": "object"}},
                impl_path=str(file_path.resolve()),
                description=res_def.description,
                owner_id=f"dev_session:{session_id}",
            )
            resource_ids.append(res_def.id)
    await db.commit()
    return resource_ids


async def _unregister_dev_resources(db: AsyncSession, session_id: str) -> None:
    """清理会话注册的临时资源。"""
    await db.execute(
        sa_delete(SkillTool).where(SkillTool.owner_id == f"dev_session:{session_id}")
    )
    await db.commit()


async def _ensure_owned(dev_session: DevSession, user: User) -> None:
    """校验会话归属；否则 404（不泄露会话存在性）。"""
    if dev_session.user_id != str(user.id):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "调试会话不存在"},
        )


def _messages_url(request_url: str, session_id: uuid.UUID) -> str:
    """构造 messages 端点完整 URL（基于当前请求的 scheme/host）。"""
    return f"{request_url.rstrip('/')}/api/plugins/dev-session/{session_id}/messages"


@router.post("", response_model=DevSessionOut, status_code=201)
async def create_dev_session(
    payload: DevSessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> DevSessionOut:
    """创建调试会话：校验 manifest + 依赖 → 注册临时资源 → 返回 session_id。"""
    manifest = payload.manifest

    # 1. 结构校验（与部署一致）
    try:
        validate_manifest(manifest)
    except PluginValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc

    # 2. 校验每个 skill/tool 的 code 非空
    for r in [*manifest.skills, *manifest.tools]:
        if not r.code or not r.code.strip():
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "plugin_invalid",
                    "message": f"调试模式要求 {r.id} 附带源码 code（远程执行需要）",
                },
            )

    # 3. 依赖解析（与部署一致）
    missing = await check_dependencies(db, manifest.depends_on)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "dependency_missing",
                "message": f"依赖不满足: {', '.join(missing)}",
            },
        )

    # 4. 创建会话（含同用户单会话限制）
    try:
        dev_session = await dev_manager.create(
            user_id=str(user.id),
            manifest=manifest,
            resource_ids=[],  # 先在管理器占位，注册后填充
            storage_dir=Path(),
        )
    except DevSessionError as exc:
        raise HTTPException(status_code=429, detail={"code": exc.code, "message": str(exc)}) from exc

    # 5. 写入临时代码 + 注册资源
    session_id = uuid.UUID(dev_session.session_id)
    storage_dir = _session_storage_dir(dev_session.session_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    try:
        resource_ids = await _register_dev_resources(db, manifest, dev_session.session_id, storage_dir)
    except Exception as exc:
        await dev_manager.delete(dev_session.session_id)
        raise HTTPException(
            status_code=422,
            detail={"code": "plugin_invalid", "message": f"资源注册失败: {exc}"},
        ) from exc

    # 更新会话：storage_dir + resource_ids
    dev_session.storage_dir = storage_dir
    dev_session.resource_ids = resource_ids

    # depends_on 资源 id 一并加入可用列表
    from agentplatform.core.registry.service import split_dependency

    dep_ids = [split_dependency(d)[0] for d in manifest.depends_on]
    all_ids = list(dict.fromkeys(dep_ids + resource_ids))
    dev_session.resource_ids = all_ids

    messages_url = _messages_url(str(request.base_url), session_id)
    return DevSessionOut(
        session_id=session_id,
        messages_url=messages_url,
        ttl_seconds=dev_session.ttl,
        resources=all_ids,
    )


@router.post("/{session_id}/messages")
async def send_dev_message(
    session_id: uuid.UUID,
    payload: DevSessionMessageRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """发送调试消息，返回 SSE 流（delta / tool_call / done / error）。"""
    dev_session = await dev_manager.get(str(session_id))
    if dev_session is None:
        raise HTTPException(
            status_code=410,
            detail={"code": "session_expired", "message": "调试会话不存在或已过期"},
        )
    await _ensure_owned(dev_session, user)

    if dev_session.interaction_count >= settings.dev_session_max_interactions:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "too_many_interactions",
                "message": "调试会话交互次数已达上限",
            },
        )

    async def event_stream() -> AsyncIterator[str]:
        text_parts: list[str] = []
        try:
            dev_session.touch()
            async for ev in _dev_chat_stream(db, dev_session, payload.content):
                if ev.type == "delta" and ev.text:
                    text_parts.append(ev.text)
                    yield sse("delta", {"block_index": 0, "text": ev.text})
                elif ev.type == "tool_call" and ev.tool_trace is not None:
                    t = ev.tool_trace
                    yield sse(
                        "tool_call",
                        {
                            "kind": t.id.split(":", 1)[0],
                            "name": t.id,
                            "args": t.args,
                            "result": t.result,
                        },
                    )
                elif ev.type == "done":
                    yield sse("done", {"ok": True})
        except Exception as exc:  # noqa: BLE001  SSE 内兜底
            yield sse("error", {"code": "agent_error", "message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def _dev_chat_stream(db: AsyncSession, dev_session: DevSession, content: str):
    """复用 stream_agent 的远程调试对话流。"""
    from agentplatform.core.agent.loop import stream_agent as _stream_agent
    from agentplatform.core.chat.service import make_llm_client

    # 追加用户消息到内存历史
    dev_session.history.append({"role": "user", "content": content})

    client = await make_llm_client(db, dev_session.manifest.model)

    async for ev in _stream_agent(
        db,
        client,
        resource_ids=dev_session.resource_ids,
        user_message=content,
        history=dev_session.history[:-1],
        owner_id=dev_session.user_id,
    ):
        yield ev

    # 最终 assistant 文本写入历史（内存态，会话结束即丢弃）
    if dev_session.history and dev_session.history[-1]["role"] == "user":
        dev_session.history.append({"role": "assistant", "content": ""})


@router.delete("/{session_id}")
async def delete_dev_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """主动清理调试会话（CLI exit 时调用）。"""
    dev_session = await dev_manager.get(str(session_id))
    if dev_session is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "调试会话不存在或已过期"},
        )
    await _ensure_owned(dev_session, user)
    await _unregister_dev_resources(db, str(session_id))
    await dev_manager.delete(str(session_id))
    return {"ok": True}


@router.post("/{session_id}/heartbeat")
async def heartbeat_dev_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """心跳续期：刷新 TTL，返回剩余秒数。"""
    dev_session = await dev_manager.get(str(session_id))
    if dev_session is None:
        raise HTTPException(
            status_code=410,
            detail={"code": "session_expired", "message": "调试会话不存在或已过期"},
        )
    await _ensure_owned(dev_session, user)
    remaining = await dev_manager.touch(str(session_id))
    return {"ok": True, "ttl_seconds": remaining}
