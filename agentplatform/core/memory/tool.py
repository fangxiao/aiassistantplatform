"""tool:memory —— 用户长期记忆读写(平台内置,M15 P1)。

agent 在对话中自然地"记住"用户偏好与事实(save),或查看/遗忘(list/delete);
记忆在每次会话组装时注入 system prompt(见 agent/messages.build_system_prompt)。
"""

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.memory import service as memory_service

MEMORY_TOOL_ID = "tool:memory"

RESOURCE: dict = {
    "id": MEMORY_TOOL_ID,
    "kind": "tool",
    "name": "memory",
    "version": "1.0.0",
    "description": (
        "用户的长期记忆。当用户表达偏好、告知个人事实、要求记住某事时,调用 save;"
        "需要回忆用户相关信息时调用 list;用户要求忘记某条时调用 delete。"
        "例:「以后回答简洁一点」「记住我在做 AI 平台」「忘掉那条关于xx的记忆」。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "list", "delete"],
                    "description": "save=记住一条;list=查看全部;delete=按 memory_id 遗忘",
                },
                "content": {"type": "string", "description": "一句话事实/偏好(save 时必填)"},
                "memory_id": {"type": "string", "description": "记忆 id(delete 时必填,从 list 获取)"},
            },
            "required": ["action"],
        },
        "returns": {"type": "string", "description": "操作结果(JSON)"},
    },
}


async def run(db: AsyncSession, user_id: str, args: dict) -> str:
    """执行记忆操作;返回 JSON 字符串回填 agent loop。"""
    action = (args.get("action") or "").strip()
    try:
        if action == "save":
            content = str(args.get("content") or "").strip()
            if not content:
                return json.dumps({"ok": False, "error": "content 不能为空"}, ensure_ascii=False)
            row = await memory_service.add_memory(db, str(user_id), content)
            return json.dumps(
                {"ok": True, "action": "save", "memory_id": str(row.id), "content": row.content,
                 "message": f"已记住:{row.content}"},
                ensure_ascii=False,
            )
        if action == "list":
            rows = await memory_service.list_memories(db, str(user_id))
            return json.dumps(
                {
                    "ok": True,
                    "action": "list",
                    "memories": [{"memory_id": str(r.id), "content": r.content} for r in rows[:30]],
                    "count": len(rows),
                    "message": f"共 {len(rows)} 条记忆",
                },
                ensure_ascii=False,
            )
        if action == "delete":
            raw = args.get("memory_id")
            if not raw:
                return json.dumps({"ok": False, "error": "缺少 memory_id(先 list 获取)"}, ensure_ascii=False)
            ok = await memory_service.remove_memory(db, str(user_id), uuid.UUID(str(raw)))
            return json.dumps(
                {"ok": ok, "action": "delete", "message": "已遗忘" if ok else "记忆不存在"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"ok": False, "error": f"未知 action: {action!r}(支持 save/list/delete)"},
            ensure_ascii=False,
        )
    except ValueError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
