"""插件部署与管理 API(设计 005 §5)。

deploy 接收清单 JSON(M9 CLI 会解析 plugin.yaml 后调用);MVP 不做鉴权。
错误经 PluginError -> 422 {error:{code,message}}(005 §1)。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import (
    get_current_user,
    get_optional_current_user,
)
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.db.session import get_session
from agentplatform.core.kb import service as kb_service
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


class MountedKbsIn(BaseModel):
    """助手挂载知识库请求(全量覆盖;设计 008 §4.3)。"""

    kb_ids: list[uuid.UUID]


@router.post("/deploy", response_model=PluginOut, status_code=201)
async def deploy(
    payload: PluginManifest,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_current_user),
) -> PluginOut:
    """部署插件:依赖校验通过后登记插件及其自有 skill/tool。

    ADR 0007:插件名全局唯一,同名重部署原地覆盖(保留 UUID 与历史会话)。
    """
    try:
        owner_id = str(user.id) if user else "anonymous"
        plugin = await deploy_plugin(session, payload, owner_id=owner_id)
        await session.commit()
    except PluginError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    return to_out(plugin)




@router.get("", response_model=list[PluginOut])
async def plugins_list(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[PluginOut]:
    """我的插件列表(按部署时间倒序)。"""
    return [to_out(p) for p in await list_plugins(session)]


@router.post("/{plugin_id}/enable", response_model=PluginOut)
async def enable(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PluginOut:
    return await _set_status(plugin_id, PluginStatus.active, session)


@router.post("/{plugin_id}/disable", response_model=PluginOut)
async def disable(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
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


@router.put("/{plugin_id}/mounted-kbs", response_model=PluginOut)
async def set_mounted_kbs(
    plugin_id: uuid.UUID,
    payload: MountedKbsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> PluginOut:
    """给助手挂载知识库(全量覆盖;仅 developer;仅 public+active 库,设计 008 §4.3)。"""
    if user.role != UserRole.developer:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "仅 developer 角色可挂载知识库"},
        )
    plugin = await get_plugin(session, plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"插件不存在: {plugin_id}"},
        )
    # 去重保序;逐个校验公共可读(助手挂载对全部使用者生效,不能带入私有/共享库)
    kb_ids = list(dict.fromkeys(payload.kb_ids))
    for kid in kb_ids:
        if await kb_service.get_public_kb(session, kid) is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "not_found", "message": f"知识库不存在或非公共库: {kid}"},
            )
    plugin.mounted_kb_ids = [str(k) for k in kb_ids]
    await session.commit()
    return to_out(plugin)


@router.delete("/{plugin_id}", status_code=204)
async def uninstall(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
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
