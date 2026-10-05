"""插件部署与管理 API(设计 005 §5 / 015 §5)。

角色门槛(ADR 0008 层级制):部署/挂载 require_developer;启停与审批 admin
(owner 下架自己插件豁免);"自己的插件"以 owner_id 判定,admin 豁免。
deploy 必须登录;错误经 PluginError -> 422 {error:{code,message}}(005 §1)。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import (
    is_admin,
    require_admin,
    require_developer,
)
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.kb import service as kb_service
from agentplatform.core.plugin.errors import PluginError
from agentplatform.core.plugin.loader import (
    deploy_plugin,
    get_plugin,
    is_plugin_owner,
    list_plugins,
    set_review,
    set_status,
    uninstall_plugin,
)
from agentplatform.core.plugin.manifest import PluginManifest
from agentplatform.core.plugin.model import Plugin, PluginReviewStatus, PluginStatus
from agentplatform.core.plugin.schemas import PluginOut, to_out

router = APIRouter(prefix="/plugins", tags=["plugins"])


class MountedKbsIn(BaseModel):
    """助手挂载知识库请求(全量覆盖;设计 008 §4.3)。"""

    kb_ids: list[uuid.UUID]


class ReviewIn(BaseModel):
    """审批请求(015 §5):approve 无需 reason,reject 必填。"""

    action: str  # approve / reject
    reason: str | None = None


async def _get_owned_plugin(
    plugin_id: uuid.UUID, session: AsyncSession, user: User
) -> Plugin:
    """取插件并校验 owner(admin 豁免);404 不泄露存在性。"""
    plugin = await get_plugin(session, plugin_id)
    if plugin is None or not is_plugin_owner(plugin, user):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"插件不存在: {plugin_id}"},
        )
    return plugin


@router.post("/deploy", response_model=PluginOut, status_code=201)
async def deploy(
    payload: PluginManifest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_developer),
) -> PluginOut:
    """部署插件:依赖校验通过后登记插件及其自有 skill/tool。

    ADR 0007:插件名全局唯一,同名重部署原地覆盖(保留 UUID 与历史会话)。
    ADR 0008:部署默认 pending_review,admin 审批后方全员可见。
    """
    try:
        plugin = await deploy_plugin(session, payload, owner_id=str(user.id))
        await session.commit()
    except PluginError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)}) from exc
    return to_out(plugin)


@router.get("", response_model=list[PluginOut])
async def plugins_list(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_developer),
) -> list[PluginOut]:
    """插件管理列表(developer 仅自己,admin 全量;按部署时间倒序)。"""
    rows = await list_plugins(session)
    if not is_admin(user):
        rows = [p for p in rows if p.owner_id == str(user.id)]
    return [to_out(p) for p in rows]


@router.post("/{plugin_id}/enable", response_model=PluginOut)
async def enable(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> PluginOut:
    """启用(运营动作,仅 admin)。"""
    return await _set_status(plugin_id, PluginStatus.active, session)


@router.post("/{plugin_id}/disable", response_model=PluginOut)
async def disable(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_developer),
) -> PluginOut:
    """下架:admin 任意插件;developer 仅自己的(owner 自主下架豁免)。"""
    plugin = await get_plugin(session, plugin_id)
    if plugin is None or not is_plugin_owner(plugin, user):
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"插件不存在: {plugin_id}"},
        )
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


@router.post("/{plugin_id}/review", response_model=PluginOut)
async def review(
    plugin_id: uuid.UUID,
    payload: ReviewIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_admin),
) -> PluginOut:
    """发布审批(仅 admin):approve → 全员可见;reject 必填原因。"""
    plugin = await get_plugin(session, plugin_id)
    if plugin is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": f"插件不存在: {plugin_id}"},
        )
    action = payload.action.lower()
    if action == "approve":
        status = PluginReviewStatus.approved
    elif action == "reject":
        status = PluginReviewStatus.rejected
        if not (payload.reason or "").strip():
            raise HTTPException(
                status_code=422,
                detail={"code": "validation_error", "message": "驳回必须填写原因"},
            )
    else:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "action 仅支持 approve/reject"},
        )
    await set_review(session, plugin, status, str(user.id), payload.reason)
    await session.commit()
    return to_out(plugin)


@router.post("/{plugin_id}/resubmit", response_model=PluginOut)
async def resubmit(
    plugin_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_developer),
) -> PluginOut:
    """驳回后重新提交审核(owner;回 pending_review,清空原因)。"""
    plugin = await _get_owned_plugin(plugin_id, session, user)
    if plugin.review_status != PluginReviewStatus.rejected:
        raise HTTPException(
            status_code=422,
            detail={"code": "validation_error", "message": "仅被驳回的插件可重新提交"},
        )
    await set_review(session, plugin, PluginReviewStatus.pending_review, str(user.id))
    await session.commit()
    return to_out(plugin)


@router.put("/{plugin_id}/mounted-kbs", response_model=PluginOut)
async def set_mounted_kbs(
    plugin_id: uuid.UUID,
    payload: MountedKbsIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_developer),
) -> PluginOut:
    """给助手挂载知识库(全量覆盖;仅 owner/admin)。

    设计 008 §4.3:仅 public+active 库(对全部使用者生效,不能带入私有/共享)。
    M27 例外:组织上下文包(shared)可挂——运行时 kb_search 按当前用户成员资格
    过滤,非成员检索不到,安全不变式保持(设计 021 §3);操作者须为包成员。
    """
    plugin = await _get_owned_plugin(plugin_id, session, user)
    # 去重保序;逐个校验公共可读(助手挂载对全部使用者生效,不能带入私有/共享库)
    kb_ids = list(dict.fromkeys(payload.kb_ids))
    for kid in kb_ids:
        kb = await kb_service.get_kb(session, kid)
        if kb is not None and kb.is_context_pack and kb.status == "active":
            from agentplatform.core.kb.search_tool import _is_kb_member

            if not await _is_kb_member(session, kb, str(user.id)):
                raise HTTPException(
                    status_code=403,
                    detail={"code": "forbidden", "message": f"非该上下文包成员: {kid}"},
                )
            continue
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
    user: User = Depends(require_developer),
) -> Response:
    """卸载:删除插件及其私有 skill/tool(仅 owner/admin)。"""
    plugin = await _get_owned_plugin(plugin_id, session, user)
    await uninstall_plugin(session, plugin)
    await session.commit()
    return Response(status_code=204)
