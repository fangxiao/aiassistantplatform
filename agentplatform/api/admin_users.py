"""用户管理 API(015 §6,仅 admin):角色分配、禁用/启用。

不做注册审批;线上 developer/admin 一律由此指派。禁用即 disabled_at 置当前时间,
登录与既有令牌一并失效(依赖层校验)。
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import require_admin
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.db.session import get_session

router = APIRouter(prefix="/admin/users", tags=["admin"])


class UserPatch(BaseModel):
    """角色/禁用部分更新;均可选,至少一项。"""

    role: UserRole | None = None
    disabled: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


class UserAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    nickname: str | None = None
    role: UserRole
    disabled: bool
    email_verified: bool = False  # M24 P2 B3.5:admin 可见验证状态
    created_at: datetime

    model_config = {"from_attributes": True}


def _out(u: User) -> UserAdminOut:
    return UserAdminOut(
        id=u.id, email=u.email, nickname=u.nickname,
        role=u.role, disabled=u.disabled_at is not None,
        email_verified=u.email_verified_at is not None, created_at=u.created_at,
    )


@router.get("", response_model=list[UserAdminOut])
async def list_users(
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_admin),
) -> list[UserAdminOut]:
    """用户列表(email/nickname 模糊搜索)。"""
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(User.email.ilike(like) | User.nickname.ilike(like))
    rows = await session.scalars(stmt)
    return [_out(u) for u in rows]


@router.patch("/{user_id}", response_model=UserAdminOut)
async def patch_user(
    user_id: uuid.UUID,
    payload: UserPatch,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
) -> UserAdminOut:
    """改角色/禁用(仅 admin);不可操作自己(防自锁)。"""
    if payload.role is None and payload.disabled is None:
        raise HTTPException(
            status_code=422, detail={"code": "validation_error", "message": "role 与 disabled 至少提供一项"}
        )
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "用户不存在"})
    if user.id == admin.id:
        raise HTTPException(
            status_code=422, detail={"code": "validation_error", "message": "不能修改自己的角色或禁用状态"}
        )
    if payload.role is not None:
        user.role = payload.role
    if payload.disabled is not None:
        user.disabled_at = datetime.now(UTC) if payload.disabled else None
    await session.commit()
    return _out(user)
