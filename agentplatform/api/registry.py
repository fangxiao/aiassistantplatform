"""skill/tool 注册表查询 API(设计 005 §6,只读)。

写入(注册)经插件部署流程(T4.3/T4.4),本模块不提供写接口。
错误统一为 {error: {code, message}}(005 §1),由 main.py 的异常处理落地。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.registry.model import SkillToolKind
from agentplatform.core.registry.schemas import SkillToolOut, to_out
from agentplatform.core.registry.service import latest_of_each, list_public, resolve

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/skills", response_model=list[SkillToolOut])
async def list_skills(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SkillToolOut]:
    """公共 skill 列表(每资源取最高版本)。"""
    rows = latest_of_each(await list_public(session, kind=SkillToolKind.skill))
    return [to_out(r) for r in rows]


@router.get("/tools", response_model=list[SkillToolOut])
async def list_tools(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[SkillToolOut]:
    """公共 tool 列表(每资源取最高版本)。"""
    rows = latest_of_each(await list_public(session, kind=SkillToolKind.tool))
    return [to_out(r) for r in rows]


@router.get("/{kind}/{name}", response_model=SkillToolOut)
async def get_resource(
    kind: SkillToolKind,
    name: str,
    version: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SkillToolOut:
    """资源详情;?version= 传 semver 约束(^ / ~ / 精确)时按约束解析,缺省取最高版本。"""
    resource_id = f"{kind.value}:{name}"
    row = await resolve(session, resource_id, version)
    if row is None:
        detail = f"未找到资源 {resource_id}"
        if version:
            detail += f"(约束 {version})"
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": detail})
    return to_out(row)
