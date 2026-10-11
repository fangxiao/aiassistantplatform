"""tool:study_mistakes_book —— 错题本读写(官方插件 study-mistakes)。

数据落平台插件存储原语(core/storage),按 ctx.user_id 隔离;字段结构、
艾宾浩斯节奏是插件自己的领域逻辑(分层红线见 plugins/README.md)。
"""

import json
from datetime import UTC, datetime, timedelta

from agentplatform.core.storage import service as store
from agentplatform.sdk import tool

PLUGIN_NAME = "study-mistakes"
COLLECTION = "mistakes"

# 艾宾浩斯间隔(天):答对进入下一档,答错回第 1 档
INTERVAL_DAYS = [1, 2, 4, 7, 15]


def _now() -> datetime:
    return datetime.now(UTC)


def _next_review(stage: int) -> str:
    days = INTERVAL_DAYS[min(max(stage, 1), len(INTERVAL_DAYS)) - 1]
    return (_now() + timedelta(days=days)).date().isoformat()


def _result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@tool(
    id="tool:study_mistakes_book",
    version="0.1.0",
    description="错题本读写:add=录入;list=列错题;due=今日到期;grade=复习回炉/进阶;delete=删除。数据按学生账号隔离",
    schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "due", "grade", "delete"],
                "description": "add=录入;list=列错题;due=今日到期;grade=复习回炉/进阶;delete=删除",
            },
            "subject": {"type": "string", "description": "学科(add 必填;list 可按学科过滤)"},
            "topic": {"type": "string", "description": "章节/知识点(可选)"},
            "question": {"type": "string", "description": "题面(add 必填)"},
            "wrong_answer": {"type": "string", "description": "学生的错解(可选)"},
            "correct_answer": {"type": "string", "description": "正确答案(可选)"},
            "cause": {"type": "string", "description": "错因(可选)"},
            "mistake_id": {"type": "string", "description": "错题 id(grade/delete 必填,list/due 返回中获取)"},
            "correct": {"type": "boolean", "description": "grade 时:本次是否答对"},
            "as_of": {"type": "string", "description": "due 的截止日期(ISO,缺省=今天)"},
        },
        "required": ["action"],
    },
)
async def run(ctx=None, action: str = "list", **fields) -> str:
    """错题本操作分派。ctx 由平台注入(执行者身份);dev 模式无 ctx 时拒绝。"""
    if ctx is None or not getattr(ctx, "user_id", None):
        return _result({"ok": False, "error": "缺少执行者身份(ctx),存储原语仅在平台服务端可用"})

    from agentplatform.core.db.engine import SessionLocal

    action = (action or "list").strip().lower()
    try:
        async with SessionLocal() as db:
            if action == "add":
                return await _add(db, ctx, fields)
            if action == "list":
                return await _list(db, ctx, fields)
            if action == "due":
                return await _due(db, ctx, fields)
            if action == "grade":
                return await _grade(db, ctx, fields)
            if action == "delete":
                return await _delete(db, ctx, fields)
            return _result({"ok": False, "error": f"未知 action: {action}"})
    except Exception as exc:  # noqa: BLE001  错误回填给 LLM
        return _result({"ok": False, "error": str(exc)})


async def _add(db, ctx, fields: dict) -> str:
    subject = str(fields.get("subject") or "").strip()
    question = str(fields.get("question") or "").strip()
    if not subject or not question:
        return _result({"ok": False, "error": "add 需要 subject(学科) 与 question(题面) 两个必填字段"})
    data = {
        "subject": subject,
        "topic": str(fields.get("topic") or "").strip(),
        "question": question,
        "wrong_answer": str(fields.get("wrong_answer") or "").strip(),
        "correct_answer": str(fields.get("correct_answer") or "").strip(),
        "cause": str(fields.get("cause") or "").strip(),
        "stage": 1,
        "next_review_at": _next_review(1),
        "created_at": _now().isoformat(),
        "review_count": 0,
    }
    res = await store.put_doc(
        db, plugin=PLUGIN_NAME, user_id=ctx.user_id, collection=COLLECTION, data=data
    )
    await db.commit()
    return _result(
        {
            "ok": True,
            "action": "add",
            "mistake_id": res["doc_id"],
            "message": f"已录入错题本(第1轮),下次复习:{data['next_review_at'][:10]}",
        }
    )


async def _list(db, ctx, fields: dict) -> str:
    filters = []
    if fields.get("subject"):
        filters.append(("subject", "eq", str(fields["subject"]).strip()))
    docs = await store.list_docs(
        db, plugin=PLUGIN_NAME, user_id=ctx.user_id, collection=COLLECTION,
        filters=filters or None, limit=50,
    )
    return _result({"ok": True, "action": "list", "count": len(docs), "mistakes": docs})


async def _due(db, ctx, fields: dict) -> str:
    # as_of 归一为纯日期(模型可能传完整 ISO,也可能只传日期);存储侧同为日期串
    as_of = str(fields.get("as_of") or "").strip()[:10] or _now().date().isoformat()
    docs = await store.list_docs(
        db, plugin=PLUGIN_NAME, user_id=ctx.user_id, collection=COLLECTION,
        filters=[("next_review_at", "lte", as_of)],
        order_by="next_review_at", desc=False, limit=50,
    )
    return _result({"ok": True, "action": "due", "as_of": as_of[:10], "count": len(docs), "mistakes": docs})


async def _grade(db, ctx, fields: dict) -> str:
    mistake_id = str(fields.get("mistake_id") or "").strip()
    if not mistake_id:
        return _result({"ok": False, "error": "grade 需要 mistake_id(due/list 返回中获取)"})
    correct = bool(fields.get("correct", True))
    doc = await store.get_doc(
        db, plugin=PLUGIN_NAME, user_id=ctx.user_id, collection=COLLECTION, doc_id=mistake_id
    )
    if doc is None:
        return _result({"ok": False, "error": f"错题不存在: {mistake_id}"})
    stage = int(doc.get("stage") or 1)
    if correct:
        stage = min(stage + 1, len(INTERVAL_DAYS))
    else:
        stage = 1
    doc["stage"] = stage
    doc["review_count"] = int(doc.get("review_count") or 0) + 1
    doc["last_graded_at"] = _now().isoformat()
    doc["next_review_at"] = _next_review(stage)
    await store.put_doc(
        db, plugin=PLUGIN_NAME, user_id=ctx.user_id, collection=COLLECTION, doc_id=mistake_id, data=doc
    )
    await db.commit()
    verdict = "✅ 答对,进阶" if correct else "🔁 答错,回炉"
    return _result(
        {
            "ok": True,
            "action": "grade",
            "mistake_id": mistake_id,
            "message": f"{verdict}:第{stage}轮,下次复习:{doc['next_review_at'][:10]}",
            "stage": stage,
        }
    )


async def _delete(db, ctx, fields: dict) -> str:
    mistake_id = str(fields.get("mistake_id") or "").strip()
    removed = await store.delete_doc(
        db, plugin=PLUGIN_NAME, user_id=ctx.user_id, collection=COLLECTION, doc_id=mistake_id
    )
    await db.commit()
    return _result({"ok": removed, "action": "delete"})
