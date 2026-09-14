"""tool:workbench_todo —— 个人待办读写(平台内置,M14 AI 联动)。

执行体在服务端(db + 会话用户),与前端 TodoCard 共用 workbench_todos 权威存储;
loop 按 KB_SEARCH 同款特判分发(user 上下文不走通用 executor)。
"""

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.workbench import service as todo_service

WORKBENCH_TODO_TOOL_ID = "tool:workbench_todo"

# RESOURCE 形状与 builtin 其他资源一致;刻意不 import builtin.meta 以避免循环导入
# (本模块被 agent loop 顶层 import,而 builtin/__init__ 会反向登记本模块)
RESOURCE: dict[str, Any] = {
    "id": WORKBENCH_TODO_TOOL_ID,
    "kind": "tool",
    "name": "workbench_todo",
    "version": "1.0.0",
    "description": (
        "用户的个人待办清单。当用户要求记录事项、设置提醒、查看/完成/删除待办时调用;"
        "如「帮我记一下周五交周报」「我有哪些待办」「把第二条划掉」。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "toggle", "delete"],
                    "description": "add=新增;text 必填;toggle=按 todo_id 标记完成/取消;delete=按 todo_id 删除",
                },
                "text": {"type": "string", "description": "待办内容(action=add 时必填)"},
                "todo_id": {"type": "string", "description": "待办 id(action=list 返回中获取)"},
                "done": {"type": "boolean", "description": "toggle 时目标状态,缺省为切换为已完成"},
            },
            "required": ["action"],
        },
        "returns": {"type": "string", "description": "操作结果(JSON):ok/待办列表/错误信息"},
    },
}


async def run(db: AsyncSession, user_id: str, args: dict) -> str:
    """执行待办操作;返回 JSON 字符串回填 agent loop。user_id 为会话用户。"""
    action = (args.get("action") or "").strip()
    try:
        if action == "add":
            row = await todo_service.add_todo(db, user_id, str(args.get("text") or ""), origin="ai")
            return json.dumps(
                {"ok": True, "action": "add", "todo": _out(row),
                 "message": f"已记入待办:{row.text}"},
                ensure_ascii=False,
            )
        if action == "list":
            rows = await todo_service.list_todos(db, user_id)
            open_rows = [t for t in rows if not t.done]
            return json.dumps(
                {
                    "ok": True,
                    "action": "list",
                    "todos": [_out(t) for t in rows[:20]],
                    "open_count": len(open_rows),
                    "message": f"共 {len(rows)} 条待办,未完成 {len(open_rows)} 条",
                },
                ensure_ascii=False,
            )
        if action in ("toggle", "delete"):
            raw = args.get("todo_id")
            if not raw:
                return json.dumps({"ok": False, "error": "缺少 todo_id(先 list 获取)"}, ensure_ascii=False)
            todo_id = uuid.UUID(str(raw))
            if action == "toggle":
                done = bool(args.get("done", True))
                row = await todo_service.set_done(db, user_id, todo_id, done)
                if row is None:
                    return json.dumps({"ok": False, "error": "待办不存在或无权操作"}, ensure_ascii=False)
                state = "已完成" if row.done else "恢复未完成"
                return json.dumps(
                    {"ok": True, "action": "toggle", "todo": _out(row), "message": f"{row.text}:{state}"},
                    ensure_ascii=False,
                )
            ok = await todo_service.remove_todo(db, user_id, todo_id)
            return json.dumps(
                {"ok": ok, "action": "delete", "message": "已删除" if ok else "待办不存在或无权操作"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": False, "error": f"未知 action: {action!r}(支持 add/list/toggle/delete)"},
            ensure_ascii=False,
        )
    except ValueError as exc:  # 非法 uuid 等
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)


def _out(row) -> dict:
    return {
        "todo_id": str(row.id),
        "text": row.text,
        "done": row.done,
        "origin": row.origin,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
