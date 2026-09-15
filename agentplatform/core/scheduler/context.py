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
    if kind not in ("briefing", "inspection"):
        return {}
    todos = await todo_service.list_todos(db, str(user_id))
    open_todos = [t.text for t in todos if not t.done]
    return {
        "kbs": await _kb_activity(db, str(user_id)),
        "pending_todos": {"count": len(open_todos), "items": open_todos[:5]},
    }


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
            "你是平台巡检助手。请检查以下知识库与数据源状态数据,"
            "仅报告异常项(同步失败/部分失败/长期未同步)与对应的处理建议;"
            "全部正常时输出「巡检通过:全部知识库与数据源状态正常」。"
            "100 字以内,直接输出结论。数据:\n"
        )
    else:
        return extra_prompt.strip()
    if extra_prompt.strip():
        base += f"\n用户补充要求:{extra_prompt.strip()}\n"
    return base + json.dumps(context, ensure_ascii=False, default=str)
