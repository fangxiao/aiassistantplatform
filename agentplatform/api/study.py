"""学习工作台 API(M36 学生工作台)。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.dependencies import get_current_user
from agentplatform.core.auth.model import User
from agentplatform.core.db.session import get_session
from agentplatform.core.study import daily_summary, study_stats

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/stats")
async def get_study_stats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """学习进度卡数据(今日/本周/streak/各科)。"""
    return await study_stats(session, str(user.id))


@router.get("/daily-summary")
async def get_daily_summary(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """家长日报文本(也可直接查看)。"""
    text = await daily_summary(session, str(user.id))
    return {"text": text}
