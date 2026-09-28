"""洞察 API(产品成熟度①③):成本汇总 + 管理面板数据。

角色拆两档(015 §4.1,ADR 0008):
- admin:全平台口径(/insights/costs 无过滤、管理面板全部端点);
- developer:仅自己插件口径(/insights/costs 按 owner_id 过滤)。
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import (
    get_current_user,
    is_admin,
    is_developer,
    require_admin,
)
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.message.model import Message
from agentplatform.core.plugin.model import Plugin
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun
from agentplatform.core.session.model import Session

router = APIRouter(prefix="/insights", tags=["insights"])


async def _own_plugin_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """developer 自己名下的插件 id 集合(insights 范围过滤)。"""
    rows = await db.scalars(select(Plugin.id).where(Plugin.owner_id == str(user.id)))
    return list(rows)


class CostSummary(BaseModel):
    total_tokens: int
    chat_tokens: int
    task_tokens: int
    last_7d_tokens: int
    by_day: list[dict]  # [{date, tokens}]
    by_assistant: list[dict]  # [{name, tokens, sessions}]
    by_task: list[dict]  # [{name, tokens, runs}]


@router.get("/costs", response_model=CostSummary)
async def cost_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CostSummary:
    """成本汇总:admin 全平台;developer 仅自己插件(对话/定时任务 token,按日/助手/任务分布)。"""
    if not is_developer(user):
        raise HTTPException(
            status_code=403, detail={"code": "forbidden", "message": "仅管理员或开发者可访问"}
        )
    scope_own: list[uuid.UUID] | None = None if is_admin(user) else await _own_plugin_ids(db, user)
    own_sessions = None
    own_tasks = None
    if scope_own is not None:
        own_sessions = select(Session.id).where(Session.plugin_id.in_(scope_own or [uuid.uuid4()]))
        own_tasks = select(ScheduledTask.id).where(
            ScheduledTask.plugin_id.in_(scope_own or [uuid.uuid4()])
        )
    since = datetime.now(UTC) - timedelta(days=days)

    # 对话 token:assistant 消息 join sessions 取 plugin 名称
    chat_stmt = select(func.coalesce(func.sum(Message.tokens), 0)).where(Message.role == "assistant")
    chat_7d_stmt = chat_stmt.where(Message.created_at >= datetime.now(UTC) - timedelta(days=7))
    if own_sessions is not None:
        chat_stmt = chat_stmt.where(Message.session_id.in_(own_sessions))
        chat_7d_stmt = chat_7d_stmt.where(Message.session_id.in_(own_sessions))
    chat_total = await db.scalar(chat_stmt) or 0
    chat_7d = await db.scalar(chat_7d_stmt) or 0

    by_day_stmt = (
        select(
            func.date_trunc("day", Message.created_at).label("d"),
            func.sum(Message.tokens).label("t"),
        )
        .where(Message.role == "assistant", Message.created_at >= since)
        .group_by("d")
        .order_by("d")
    )
    if own_sessions is not None:
        by_day_stmt = by_day_stmt.where(Message.session_id.in_(own_sessions))
    by_day_rows = await db.execute(by_day_stmt)
    by_day = [{"date": str(r[0].date()), "tokens": int(r[1] or 0)} for r in by_day_rows]

    by_asst_stmt = (
        select(
            func.coalesce(Plugin.name, "平台通用助手").label("name"),
            func.sum(Message.tokens).label("t"),
            func.count(func.distinct(Message.session_id)).label("s"),
        )
        .join(Session, Message.session_id == Session.id)
        .outerjoin(Plugin, Session.plugin_id == Plugin.id)
        .where(Message.role == "assistant")
        .group_by("name")
        .order_by(func.sum(Message.tokens).desc().nullslast())
        .limit(10)
    )
    if own_sessions is not None:
        by_asst_stmt = by_asst_stmt.where(Session.plugin_id.in_(scope_own or [uuid.uuid4()]))
    by_asst_rows = await db.execute(by_asst_stmt)
    by_assistant = [{"name": r[0], "tokens": int(r[1] or 0), "sessions": int(r[2])} for r in by_asst_rows]

    task_total_stmt = select(func.coalesce(func.sum(TaskRun.tokens), 0))
    by_task_stmt = (
        select(
            func.coalesce(ScheduledTask.name, "(已删除任务)").label("name"),
            func.sum(TaskRun.tokens).label("t"),
            func.count(TaskRun.id).label("runs"),
        )
        .outerjoin(ScheduledTask, TaskRun.task_id == ScheduledTask.id)
        .group_by("name")
        .order_by(func.sum(TaskRun.tokens).desc().nullslast())
        .limit(10)
    )
    if own_tasks is not None:
        task_total_stmt = task_total_stmt.where(TaskRun.task_id.in_(own_tasks))
        by_task_stmt = by_task_stmt.where(TaskRun.task_id.in_(own_tasks))
    task_total = await db.scalar(task_total_stmt) or 0
    by_task_rows = await db.execute(by_task_stmt)
    by_task = [{"name": r[0], "tokens": int(r[1] or 0), "runs": int(r[2])} for r in by_task_rows]

    return CostSummary(
        total_tokens=int(chat_total) + int(task_total),
        chat_tokens=int(chat_total),
        task_tokens=int(task_total),
        last_7d_tokens=int(chat_7d),
        by_day=by_day,
        by_assistant=by_assistant,
        by_task=by_task,
    )


class AdminUserRow(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    session_count: int
    message_tokens: int
    task_count: int


@router.get("/admin/users", response_model=list[AdminUserRow])
async def admin_users(
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_admin),
) -> list[AdminUserRow]:
    """用户列表与用量(管理面板,仅 admin)。"""
    from agentplatform.core.auth.model import User as UserModel

    users = list(await db.scalars(select(UserModel).order_by(UserModel.created_at.desc())))
    out: list[AdminUserRow] = []
    for u in users:
        s_cnt = await db.scalar(
            select(func.count()).select_from(Session).where(Session.user_id == str(u.id))
        ) or 0
        m_tok = await db.scalar(
            select(func.coalesce(func.sum(Message.tokens), 0))
            .join(Session, Message.session_id == Session.id)
            .where(Session.user_id == str(u.id))
        ) or 0
        t_cnt = await db.scalar(
            select(func.count()).select_from(ScheduledTask).where(ScheduledTask.user_id == str(u.id))
        ) or 0
        out.append(
            AdminUserRow(
                id=u.id, email=u.email, role=u.role.value,
                created_at=u.created_at, session_count=int(s_cnt),
                message_tokens=int(m_tok), task_count=int(t_cnt),
            )
        )
    return out


class PlatformOverview(BaseModel):
    users: int
    sessions: int
    assistants: int
    knowledge_bases: int
    scheduled_tasks_active: int
    documents_ready: int


@router.get("/admin/overview", response_model=PlatformOverview)
async def platform_overview(
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_admin),
) -> PlatformOverview:
    """平台总览卡片(管理面板,仅 admin)。"""
    from agentplatform.core.auth.model import User as UserModel
    from agentplatform.core.kb.model import KbDocument, KbDocumentStatus, KnowledgeBase

    async def _count(model, *where):
        stmt = select(func.count()).select_from(model)
        if where:
            stmt = stmt.where(*where)
        return int(await db.scalar(stmt) or 0)

    return PlatformOverview(
        users=await _count(UserModel),
        sessions=await _count(Session),
        assistants=await _count(Plugin, Plugin.status == "active"),
        knowledge_bases=await _count(KnowledgeBase, KnowledgeBase.status == "active"),
        scheduled_tasks_active=await _count(ScheduledTask, ScheduledTask.enabled.is_(True)),
        documents_ready=await _count(KbDocument, KbDocument.status == KbDocumentStatus.ready),
    )


class ActionLogRow(BaseModel):
    id: uuid.UUID
    user_id: str
    method: str
    url: str
    outcome: str
    status_code: int | None
    detail: str | None
    created_at: datetime


@router.get("/actions", response_model=list[ActionLogRow])
async def action_logs(
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_admin),
) -> list[ActionLogRow]:
    """动作审计记录(产品成熟度④/M17 P1,仅 admin):http_request 执行/拒绝/取消留痕。"""
    from agentplatform.core.agent.action_log import ActionLog

    rows = await db.scalars(
        select(ActionLog).order_by(ActionLog.created_at.desc()).limit(min(limit, 200))
    )
    return [
        ActionLogRow(
            id=r.id, user_id=r.user_id, method=r.method, url=r.url, outcome=r.outcome,
            status_code=r.status_code, detail=r.detail, created_at=r.created_at,
        )
        for r in rows
    ]
