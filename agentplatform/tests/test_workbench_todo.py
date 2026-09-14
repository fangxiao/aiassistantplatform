"""工作台待办测试(M14 AI 联动):服务 CRUD、工具执行(user 隔离)、API。"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.workbench import service as todo_service
from agentplatform.core.workbench.todo_tool import run as run_todo_tool


@pytest.fixture
async def user_a(session: AsyncSession):
    return await create_user(session, f"wa-{uuid.uuid4()}@test.dev", "password123", UserRole.user)


@pytest.fixture
async def user_b(session: AsyncSession):
    return await create_user(session, f"wb-{uuid.uuid4()}@test.dev", "password123", UserRole.user)


class TestTodoService:
    async def test_add_list_toggle(self, session: AsyncSession, user_a) -> None:
        row = await todo_service.add_todo(session, str(user_a.id), "周五交周报")
        await todo_service.add_todo(session, str(user_a.id), "已完成事项", origin="ai")
        rows = await todo_service.list_todos(session, str(user_a.id))
        assert len(rows) == 2
        assert all(not r.done for r in rows)

        done = await todo_service.set_done(session, str(user_a.id), row.id, True)
        assert done is not None and done.done and done.done_at is not None
        rows2 = await todo_service.list_todos(session, str(user_a.id))
        assert sum(1 for r in rows2 if r.done) == 1

    async def test_user_isolation(self, session: AsyncSession, user_a, user_b) -> None:
        """AI 写入的待办按会话用户隔离:B 看不到也改不了 A 的待办。"""
        row = await todo_service.add_todo(session, str(user_a.id), "A 的私事")
        assert await todo_service.set_done(session, str(user_b.id), row.id, True) is None
        assert await todo_service.remove_todo(session, str(user_b.id), row.id) is False
        assert [t.text for t in await todo_service.list_todos(session, str(user_b.id))] == []

    async def test_clear_completed(self, session: AsyncSession, user_a) -> None:
        r1 = await todo_service.add_todo(session, str(user_a.id), "one")
        r2 = await todo_service.add_todo(session, str(user_a.id), "two")
        await todo_service.set_done(session, str(user_a.id), r1.id, True)
        removed = await todo_service.clear_completed(session, str(user_a.id))
        assert removed == 1
        remaining = [t.text for t in await todo_service.list_todos(session, str(user_a.id))]
        assert remaining == ["two"]
        _ = r2


class TestTodoTool:
    async def test_add_and_list_via_tool(self, session: AsyncSession, user_a) -> None:
        """AI 联动主链路:LLM 以 {action:add,text} 调用 → 落库 origin=ai。"""
        out1 = await run_todo_tool(session, str(user_a.id), {"action": "add", "text": "下午三点开会"})
        import json

        data = json.loads(out1)
        assert data["ok"] and data["todo"]["origin"] == "ai" and "已记入待办" in data["message"]

        out2 = await run_todo_tool(session, str(user_a.id), {"action": "list"})
        data2 = json.loads(out2)
        assert data2["open_count"] == 1 and data2["todos"][0]["text"] == "下午三点开会"

    async def test_toggle_missing_and_bad_action(self, session: AsyncSession, user_a) -> None:
        import json

        out = await run_todo_tool(session, str(user_a.id), {"action": "toggle", "todo_id": str(uuid.uuid4())})
        assert json.loads(out)["ok"] is False
        out2 = await run_todo_tool(session, str(user_a.id), {"action": "hack"})
        assert json.loads(out2)["ok"] is False

    async def test_tool_user_isolation(self, session: AsyncSession, user_a, user_b) -> None:
        import json

        out = await run_todo_tool(session, str(user_a.id), {"action": "add", "text": "A 的待办"})
        todo_id = json.loads(out)["todo"]["todo_id"]
        out_b = await run_todo_tool(session, str(user_b.id), {"action": "toggle", "todo_id": todo_id})
        assert json.loads(out_b)["ok"] is False


@pytest.mark.asyncio
class TestTodosApi:
    async def test_crud_flow(self, client) -> None:
        r = await client.post("/api/workbench/todos", json={"text": "写周报"})
        assert r.status_code == 201
        tid = r.json()["id"]
        assert r.json()["origin"] == "manual"

        listed = await client.get("/api/workbench/todos")
        assert any(t["id"] == tid for t in listed.json())

        r2 = await client.patch(f"/api/workbench/todos/{tid}", json={"done": True})
        assert r2.status_code == 200 and r2.json()["done"] is True

        r3 = await client.delete("/api/workbench/todos/completed")
        assert r3.status_code == 200 and r3.json()["removed"] == 1

        r4 = await client.delete(f"/api/workbench/todos/{tid}")
        assert r4.status_code == 404  # 已被清空

    async def test_import_and_validation(self, client) -> None:
        r = await client.post("/api/workbench/todos/import", json=["本地待办一", "本地待办二", ""])
        assert r.status_code == 200 and r.json()["imported"] == 2
        listed = (await client.get("/api/workbench/todos")).json()
        assert {t["text"] for t in listed} >= {"本地待办一", "本地待办二"}

        r2 = await client.post("/api/workbench/todos", json={"text": ""})
        assert r2.status_code == 422
