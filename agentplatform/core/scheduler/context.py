"""任务上下文聚合模板(设计 011 §4):kind 决定注入什么数据。

与工作台前端 M14 聚合同源同义(kb 列表/数据源状态/待办 API 同一批查询),
服务端聚合供定时运行使用(前端聚合无法在后端定时上下文中复用)。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KnowledgeBase
from agentplatform.core.workbench import service as todo_service


async def _kb_activity(db: AsyncSession, user_id: str, limit: int = 8) -> list[dict]:
    """用户可见库 + 各库数据源最近同步状态(与工作台知识库动态卡同口径)。"""
    rows: list[KnowledgeBase] = await kb_service.list_visible_kbs(db, user_id)
    out: list[dict] = []
    for kb in rows[:limit]:
        from agentplatform.core.kb.connectors import service as connector_service

        sources = await connector_service.list_sources(db, kb.id)
        latest = max(
            (s for s in sources if s.last_sync_at),
            key=lambda s: s.last_sync_at,
            default=None,
        )
        out.append(
            {
                "kb": kb.name,
                "docs": kb.doc_count,
                "chunks": kb.chunk_count,
                "latest_sync": (
                    {
                        "source": latest.name,
                        "status": latest.last_status.value,
                        "at": latest.last_sync_at.isoformat() if latest.last_sync_at else None,
                        "error": latest.last_error,
                    }
                    if latest
                    else None
                ),
            }
        )
    return out


async def build_context(db: AsyncSession, user_id: str, kind: str) -> dict:
    """按任务类型聚合上下文;custom 返回空 dict(prompt 原样)。"""
    if kind not in ("briefing", "inspection", "freshness"):
        return {}
    todos = await todo_service.list_todos(db, str(user_id))
    open_todos = [t.text for t in todos if not t.done]
    context: dict = {
        "kbs": await _kb_activity(db, str(user_id)),
        "pending_todos": {"count": len(open_todos), "items": open_todos[:5]},
    }
    if kind == "freshness":
        context["freshness"] = await _doc_freshness(db, str(user_id))
    return context


async def _doc_freshness(db: AsyncSession, user_id: str, limit: int = 8) -> list[dict]:
    """文档新鲜度(P1):每库最近入库时间与最久未更新的文档(供 freshness 模板)。"""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from agentplatform.core.kb.model import KbDocument, KbDocumentStatus

    rows: list[KnowledgeBase] = await kb_service.list_visible_kbs(db, str(user_id))
    out: list[dict] = []
    for kb in rows[:limit]:
        latest_doc = await db.scalar(
            select(KbDocument)
            .where(
                KbDocument.kb_id == kb.id,
                KbDocument.status != KbDocumentStatus.deleted,
            )
            .order_by(KbDocument.created_at.desc())
            .limit(1)
        )
        stale_doc = await db.scalar(
            select(KbDocument)
            .where(
                KbDocument.kb_id == kb.id,
                KbDocument.status == KbDocumentStatus.ready,
            )
            .order_by(KbDocument.created_at.asc())
            .limit(1)
        )
        out.append(
            {
                "kb": kb.name,
                "latest_doc": (
                    {"name": latest_doc.filename, "at": latest_doc.created_at.isoformat()}
                    if latest_doc
                    else None
                ),
                "stale_doc": (
                    {
                        "name": stale_doc.filename,
                        "days": (datetime.now(UTC) - stale_doc.created_at).days,
                    }
                    if stale_doc
                    else None
                ),
            }
        )
    return out


def build_prompt(task_kind: str, extra_prompt: str, context: dict) -> str:
    """内置模板 + 用户补充要求;custom 原样。"""
    import json

    if task_kind == "briefing":
        base = (
            "你是平台工作台助手。请根据以下平台动态数据生成一段中文每日简报(180 字以内),"
            "包含:①知识库概览;②需要关注的异常(同步失败/部分失败,指出是哪个源与原因);"
            "③未完成待办提醒(有则点出最紧要的 1-2 条);④1-2 条行动建议。"
            "直接输出简报正文,不要开场白。数据:\n"
        )
    elif task_kind == "inspection":
        base = (
            "你是平台巡检助手。请检查以下知识库与数据源状态数据。"
            "**输出第一行必须是 [OK] 或 [ALERT] 标记**:发现任一异常(同步失败/部分失败/"
            "长期未同步)时首行输出 [ALERT] 并列出异常与建议;全部正常时首行输出 [OK],"
            "第二行起输出「巡检通过:全部知识库与数据源状态正常」。100 字以内,直接输出结论。数据:\n"
        )
    elif task_kind == "weekly_report":
        base = (
            "你是平台工作台助手。请根据以下平台数据生成一段中文周报(250 字以内),"
            "包含:①知识库资产概览(库数/文档量);②数据源健康度汇总;③未完成待办清单;"
            "④下周建议关注的 1-2 件事。直接输出正文,不要开场白。数据:\n"
        )
    elif task_kind == "freshness":
        base = (
            "你是知识库维护助手。请根据以下文档新鲜度数据,生成一份维护建议(150 字以内):"
            "列出最久未更新的文档与长期未同步的数据源,给出哪些需要重新同步或更新"
            "的具体建议;一切新鲜时如实说明。直接输出正文,不要开场白。数据:\n"
        )
    else:
        return extra_prompt.strip()
    if extra_prompt.strip():
        base += f"\n用户补充要求:{extra_prompt.strip()}\n"
    return base + json.dumps(context, ensure_ascii=False, default=str)
