"""学习活动服务(M36):记录/统计/streak/日报聚合。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.study.model import StudyActivity


async def record(
    session: AsyncSession, *,
    user_id: str, activity_type: str, subject: str = "other",
    count: int = 1, correct: int | None = None,
    source: str = "chat", session_id: str | None = None,
) -> StudyActivity:
    """记录一次学习行为(幂等追加)。"""
    row = StudyActivity(
        user_id=uuid.UUID(user_id),
        activity_type=activity_type,
        subject=subject,
        count=count,
        correct=correct,
        source=source,
        session_id=uuid.UUID(session_id) if session_id else None,
    )
    session.add(row)
    await session.flush()
    return row


async def study_stats(session: AsyncSession, user_id: str) -> dict:
    """学习进度卡数据:今日/本周/累计/streak/各科统计。"""
    uid = uuid.UUID(user_id)
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # 今日
    today_rows = (
        await session.scalars(
            select(StudyActivity).where(
                StudyActivity.user_id == uid,
                StudyActivity.created_at >= today_start,
            )
        )
    ).all()

    # 本周
    week_rows = (
        await session.scalars(
            select(StudyActivity).where(
                StudyActivity.user_id == uid,
                StudyActivity.created_at >= week_start,
            )
        )
    ).all()

    # 累计
    total = await session.scalar(
        select(func.count()).select_from(StudyActivity).where(StudyActivity.user_id == uid)
    )

    # streak:连续有学习行为的天数(从今天往回数)
    streak = 0
    check_date = today_start
    for _ in range(365):
        day_end = check_date + timedelta(days=1)
        has_activity = await session.scalar(
            select(func.count()).select_from(StudyActivity).where(
                StudyActivity.user_id == uid,
                StudyActivity.created_at >= check_date,
                StudyActivity.created_at < day_end,
            )
        )
        if has_activity:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    # 各科本周统计
    subjects: dict[str, int] = {}
    for r in week_rows:
        subjects[r.subject] = subjects.get(r.subject, 0) + r.count

    # 今日正确率
    today_correct = sum(r.correct or 0 for r in today_rows if r.correct is not None)
    today_total = sum(r.count for r in today_rows if r.correct is not None)

    return {
        "today_count": sum(r.count for r in today_rows),
        "today_correct": today_correct,
        "today_total_answered": today_total,
        "today_accuracy": round(today_correct / today_total * 100, 1) if today_total else None,
        "week_count": sum(r.count for r in week_rows),
        "week_subjects": subjects,
        "total_count": int(total or 0),
        "streak_days": streak,
    }


async def daily_summary(session: AsyncSession, user_id: str) -> str:
    """家长日报文本(每日推送到家长飞书)。"""
    stats = await study_stats(session, user_id)
    subjects_str = " / ".join(f"{k} {v}" for k, v in sorted(stats["week_subjects"].items()))
    acc = f"正确率 {stats['today_accuracy']}%" if stats["today_accuracy"] else ""
    status = "✅ 已完成" if stats["today_count"] > 0 else "⏳ 今日未学习"

    return (
        f"📊 今日学习情况\n\n"
        f"{status}\n"
        f"今日学习: {stats['today_count']} 项 {acc}\n"
        f"本周累计: {stats['week_count']} 项 ({subjects_str or '暂无'})\n"
        f"连续打卡: {stats['streak_days']} 天 🔥\n"
        f"累计学习: {stats['total_count']} 项"
    )
