"""插件部署与管理 API(设计 005 §5)。

deploy 接收清单 JSON(M9 CLI 会解析 plugin.yaml 后调用);MVP 不做鉴权。
错误经 PluginError -> 422 {error:{code,message}}(005 §1)。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.db.session import get_session
from agentplatform.core.plugin.errors import PluginError
from agentplatform.core.plugin.loader import (
    deploy_plugin,
    get_plugin,
    list_plugins,
    set_status,
    uninstall_plugin,
)
from agentplatform.core.plugin.manifest import PluginManifest
from agentplatform.core.plugin.model import PluginStatus
from agentplatform.core.plugin.schemas import PluginOut, to_out

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.post("/deploy", response_model=PluginOut, status_code=201)
async def deploy(
    payload: PluginManifest,
    session: AsyncSession = Depends(get_session),
) -> PluginOut:
    """部署插件:依赖校验通过后登记插件及其自有 skill/tool。"""
    try:
        plugin = await deploy_plugin(session, payload)
        await session.commit()
    except PluginError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    return to_out(plugin)


@router.get("", response_model=list[PluginOut])
async def plugins_list(
    session: AsyncSession = Depends(get_session),
) -> list[PluginOut]:
    """我的插件列表(按部署时间倒序)。"""
    return [to_out(p) for p in await list_plugins(session)]


@router.post("/{plugin_id}/enable", response_model=PluginOut)
async def enable(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PluginOut:
    return await _set_status(plugin_id, PluginStatus.active, session)


@router.post("/{plugin_id}/disable", response_model=PluginOut)
async def disable(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PluginOut:
    return await _set_status(plugin_id, PluginStatus.disabled, session)


async def _set_status(
    plugin_id: uuid.UUID, status: PluginStatus, session: AsyncSession
) -> PluginOut:
    plugin = await set_status(session, plugin_id, status)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"插件不存在: {plugin_id}"},
        )
    await session.commit()
    return to_out(plugin)


@router.delete("/{plugin_id}", status_code=204)
async def uninstall(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """卸载:删除插件及其私有 skill/tool。"""
    plugin = await get_plugin(session, plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"插件不存在: {plugin_id}"},
        )
    await uninstall_plugin(session, plugin)
    await session.commit()
    return Response(status_code=204)
