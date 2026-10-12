"""任务上下文聚合模板(设计 011 §4):kind 决定注入什么数据。

与工作台前端 M14 聚合同源同义(kb 列表/数据源状态/待办 API 同一批查询),
服务端聚合供定时运行使用(前端聚合无法在后端定时上下文中复用)。
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.kb import service as kb_service
from agentplatform.core.kb.model import KnowledgeBase
from agentplatform.core.workbench import service as todo_service

# 定时任务专用 system prompt(20261011 词汇任务事故)。
#
# 不能复用对话链路的 build_system_prompt:那段【交互规范】教模型"收集信息必须弹
# output_block 控件",对交互会话是对的,对无人值守的定时任务是反向激励——实测
# (auto 池,各 5-10 次)模型会改成向用户"确认细节",弹表单没人填,本轮作废,
# 再被 loop.py 的思考兜底把整段推理倒进产出。5 组对照实验结论:
#   现有链路                 0/5
#   仅换本 prompt            4/5   (残留失败全是去调 tool:memory)
#   本 prompt + 摘除
#   output_block/memory/todo 10/10
# 故本 prompt 必须与 service.py 的工具裁剪成对出现,单独换 prompt 不够。
SCHEDULED_TASK_SYSTEM_PROMPT = (
    "你是由 AgentPlatform 驱动的智能助手，正在执行一个**无人值守的定时任务**。\n"
    "执行期间没有用户在线：你提出的任何问题都不会得到回答，任何表单/确认框都不会被填写。\n"
    "因此你必须自行完成全部判断，并在本轮直接输出最终结果正文。\n\n"
    "【输出规范】\n"
    "1. 直接输出任务要求的成品内容；不要开场白、不要收尾寒暄、不要「我来帮你…」「请确认…」这类过渡语。\n"
    "2. 严禁输出任何交互控件（input.form / input.confirm / input.select 等），严禁向用户提问。\n"
    "3. 严禁把内部思考过程（如 The user.../I should.../Let me...）写进正文。\n\n"
    "【工具】仅当任务确实需要外部信息或动作时才调用工具；纯内容生成任务不要调用任何工具。\n\n"
    "【任务】\n"
)


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


def build_prompt(
    task_kind: str,
    extra_prompt: str,
    context: dict,
    *,
    today: date | None = None,
    last_output: str | None = None,
) -> str:
    """内置模板 + 用户补充要求;custom 原样 + 运行环境注入(日期/上期产出)。"""
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
    elif task_kind == "parent_report":
        from agentplatform.core.study import daily_summary as _ds
        # 家长日报由 service 直接生成(不走 LLM,零成本即时);此处仅作为兜底模板
        base = (
            "请根据学习活动数据生成家长日报。数据:\n"
            + json.dumps(context, ensure_ascii=False, default=str)
            + "\n格式:今日完成情况/本周累计/连续打卡天数/建议(如有)。语气简洁。"
        )
    elif task_kind == "exam_prep":
        import json as _json

        days_left = context.get("exam_days_left", "?")
        subjects = context.get("exam_subjects", "")
        base = (
            f"距离考试还有 {days_left} 天,科目:{subjects}。"
            "请根据以下错题数据,选出最可能在考试中再错的题目(优先高频错题和最近未复习的),"
            "生成一份考前冲刺练习(5-10 题)。格式:每题含题干、4 个选项(A/B/C/D)、"
            "正确答案(附在最后)、解析要点。语气鼓励。\n错题数据:\n"
            + _json.dumps(context.get("mistakes", []), ensure_ascii=False, default=str)
        )
    elif task_kind == "freshness":
        base = (
            "你是知识库维护助手。请根据以下文档新鲜度数据,生成一份维护建议(150 字以内):"
            "列出最久未更新的文档与长期未同步的数据源,给出哪些需要重新同步或更新"
            "的具体建议;一切新鲜时如实说明。直接输出正文,不要开场白。数据:\n"
        )
    else:
        # custom:用户 prompt 原样保留,但补两样定时运行无法自获的环境信息。
        # 定时运行无状态(history=[]、custom 不聚合上下文),不给日期,"每天一篇/
        # 按期轮换"类诉求无从下手;不给上期产出,模型会每期输出同一份总览
        # (20261011 文言文任务实证)。仅 custom 注入:内置模板由数据驱动天然
        # 不重复,且 inspection 首行 [OK]/[ALERT] 契约不宜引入额外变量。
        lines: list[str] = []
        if today is not None:
            wd = "一二三四五六日"[today.weekday()]
            lines.append(f"今天是 {today.year}年{today.month}月{today.day}日 星期{wd}。")
        if last_output and last_output.strip():
            head = " ".join(last_output.strip().split())[:200]
            lines.append(
                f"上一期(上次运行)的产出开头是:「{head}」。"
                "本期必须输出与上一期不同的新内容,严禁重复上一期已输出的内容。"
            )
        prefix = ("\n".join(lines) + "\n\n") if lines else ""
        return prefix + extra_prompt.strip()
    if extra_prompt.strip():
        base += f"\n用户补充要求:{extra_prompt.strip()}\n"
    return base + json.dumps(context, ensure_ascii=False, default=str)
