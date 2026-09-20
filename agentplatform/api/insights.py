"""洞察 API(产品成熟度①③):成本汇总 + 管理面板数据。"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User, UserRole
from agentplatform.core.db.session import get_session
from agentplatform.core.message.model import Message
from agentplatform.core.plugin.model import Plugin
from agentplatform.core.scheduler.model import ScheduledTask, TaskRun
from agentplatform.core.session.model import Session

router = APIRouter(prefix="/insights", tags=["insights"])


def _ensure_developer(user: User) -> None:
    if user.role != UserRole.developer:
        raise HTTPException(
            status_code=403, detail={"code": "forbidden", "message": "仅 developer 角色可访问"}
        )


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
    """成本汇总(全平台,developer):对话/定时任务 token,按日/助手/任务分布。"""
    _ensure_developer(user)
    since = datetime.now(UTC) - timedelta(days=days)

    # 对话 token:assistant 消息 join sessions 取 plugin 名称
    chat_total = await db.scalar(
        select(func.coalesce(func.sum(Message.tokens), 0)).where(Message.role == "assistant")
    ) or 0
    chat_7d = await db.scalar(
        select(func.coalesce(func.sum(Message.tokens), 0)).where(
            Message.role == "assistant", Message.created_at >= datetime.now(UTC) - timedelta(days=7)
        )
    ) or 0

    by_day_rows = await db.execute(
        select(
            func.date_trunc("day", Message.created_at).label("d"),
            func.sum(Message.tokens).label("t"),
        )
        .where(Message.role == "assistant", Message.created_at >= since)
        .group_by("d")
        .order_by("d")
    )
    by_day = [{"date": str(r[0].date()), "tokens": int(r[1] or 0)} for r in by_day_rows]

    by_asst_rows = await db.execute(
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
    by_assistant = [{"name": r[0], "tokens": int(r[1] or 0), "sessions": int(r[2])} for r in by_asst_rows]

    task_total = await db.scalar(
        select(func.coalesce(func.sum(TaskRun.tokens), 0))
    ) or 0
    by_task_rows = await db.execute(
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
    user: User = Depends(get_current_user),
) -> list[AdminUserRow]:
    """用户列表与用量(管理面板,developer)。"""
    _ensure_developer(user)
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
    user: User = Depends(get_current_user),
) -> PlatformOverview:
    """平台总览卡片(管理面板)。"""
    _ensure_developer(user)
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
