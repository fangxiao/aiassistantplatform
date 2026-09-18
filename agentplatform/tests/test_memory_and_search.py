"""长期记忆与联网搜索测试(M15 P1):memory CRUD/工具/注入、web_search 降级。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.agent.messages import build_system_prompt
from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.memory import service as memory_service
from agentplatform.core.memory.tool import run as run_memory_tool
from agentplatform.core.agent.web_search import run as run_web_search


@pytest.fixture
async def user_m(session: AsyncSession):
    return await create_user(session, f"m-{uuid.uuid4()}@test.dev", "password123", UserRole.user)


class TestMemoryService:
    async def test_add_list_remove(self, session: AsyncSession, user_m) -> None:
        await memory_service.add_memory(session, str(user_m.id), "回答风格偏好简洁")
        await memory_service.add_memory(session, str(user_m.id), "正在开发 AI 平台")
        rows = await memory_service.list_memories(session, str(user_m.id))
        assert [r.content for r in rows] == ["正在开发 AI 平台", "回答风格偏好简洁"]  # 新→旧
        assert await memory_service.remove_memory(session, str(user_m.id), rows[0].id)
        assert len(await memory_service.list_memories(session, str(user_m.id))) == 1

    async def test_user_isolation(self, session: AsyncSession, user_m) -> None:
        from agentplatform.core.auth.service import create_user as cu
        from agentplatform.core.auth.model import UserRole as UR

        other = await cu(session, f"mo-{uuid.uuid4()}@test.dev", "password123", UR.user)
        row = await memory_service.add_memory(session, str(user_m.id), "私密偏好")
        assert not await memory_service.remove_memory(session, str(other.id), row.id)
        assert await memory_service.memories_for_prompt(session, str(other.id)) == []

    async def test_lru_eviction(self, session: AsyncSession, user_m, monkeypatch) -> None:
        """每用户上限:超出淘汰最旧。"""
        monkeypatch.setattr(settings, "memory_max_per_user", 3)
        for i in range(4):
            await memory_service.add_memory(session, str(user_m.id), f"记忆{i}")
        contents = [r.content for r in await memory_service.list_memories(session, str(user_m.id))]
        assert contents == ["记忆3", "记忆2", "记忆1"]  # 记忆0 被淘汰


class TestMemoryTool:
    async def test_save_list_delete_via_tool(self, session: AsyncSession, user_m) -> None:
        import json

        out = await run_memory_tool(session, str(user_m.id), {"action": "save", "content": "用户在做 AI 平台"})
        assert json.loads(out)["ok"]
        out2 = await run_memory_tool(session, str(user_m.id), {"action": "list"})
        data = json.loads(out2)
        assert data["count"] == 1 and data["memories"][0]["content"] == "用户在做 AI 平台"
        mid = data["memories"][0]["memory_id"]
        out3 = await run_memory_tool(session, str(user_m.id), {"action": "delete", "memory_id": mid})
        assert json.loads(out3)["ok"]

    async def test_injection_in_system_prompt(self, session: AsyncSession, user_m) -> None:
        """记忆注入 system prompt(会话/定时任务共用链路)。"""
        await memory_service.add_memory(session, str(user_m.id), "偏好简洁回答")
        memories = await memory_service.memories_for_prompt(session, str(user_m.id))
        prompt = build_system_prompt([], memories=memories)
        assert "偏好简洁回答" in prompt and "长期记忆" in prompt
        # 无记忆时不注入该段
        assert "长期记忆" not in build_system_prompt([], memories=[])


class TestWebSearch:
    async def test_graceful_degradation_without_key(self, monkeypatch) -> None:
        """未配置 API key:返回明确提示而非崩溃(LLM 可告知用户)。"""
        import json

        monkeypatch.setattr(settings, "web_search_api_key", "")
        out = await run_web_search({"query": "今天天气"})
        assert json.loads(out)["ok"] is False
        assert "WEB_SEARCH_API_KEY" in json.loads(out)["error"]

    async def test_empty_query_rejected(self) -> None:
        import json

        out = await run_web_search({"query": "  "})
        assert json.loads(out)["ok"] is False


@pytest.mark.asyncio
class TestMemoryApi:
    async def test_crud_flow(self, client: AsyncClient) -> None:
        r = await client.post("/api/memory/memories", json={"content": "手动偏好:用中文"})
        assert r.status_code == 201
        mid = r.json()["id"]
        listed = (await client.get("/api/memory/memories")).json()
        assert any(m["id"] == mid for m in listed)
        assert (await client.delete(f"/api/memory/memories/{mid}")).status_code == 204

    async def test_clear_all(self, client: AsyncClient) -> None:
        await client.post("/api/memory/memories", json={"content": "a"})
        await client.post("/api/memory/memories", json={"content": "b"})
        r = await client.delete("/api/memory/memories")
        assert r.json()["removed"] == 2
        assert (await client.get("/api/memory/memories")).json() == []
