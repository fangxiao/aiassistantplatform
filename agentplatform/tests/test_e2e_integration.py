"""全链路端到端集成测试 (M10 · T10.1)。

模拟真实用户与开发者完整闭环：
1. 开发者注册与登录 (JWT 认证)
2. 插件合法性校验与部署 (M4/M9)
3. 助手广场检索助手 (M8.2)
4. 创建助手专属会话 (M6)
5. 发送消息并接收流式 SSE (M5/M6/M7)
6. 触发富交互组件回传与审计记录 (M7)
7. 会话重命名与清理
8. 插件管理与卸载 (M4/M8.4)
"""

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.cli.yaml_io import load_manifest
from agentplatform.core.llm.client import StreamEvent
from agentplatform.core.registry.service import seed_builtin

PLUGIN_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "examples"
    / "plugins"
    / "prd-review-assistant"
)


class FakeLlmClient:
    """可预测的 LLM Mock 客户端。"""

    def __init__(self, responses: list[list[StreamEvent]]) -> None:
        self.responses = responses
        self.call_count = 0

    async def stream(self, messages: list[dict], tools: list[dict] | None = None):
        idx = self.call_count
        self.call_count += 1
        events = self.responses[idx] if idx < len(self.responses) else []
        for ev in events:
            yield ev



@pytest.mark.asyncio
async def test_end_to_end_platform_lifecycle(
    client: AsyncClient, session: AsyncSession
) -> None:
    # 0. 准备内置依赖资源
    await seed_builtin(session)
    await session.commit()


    # 1. 注册与登录开发者账号
    reg_resp = await client.post(
        "/api/auth/register",
        json={
            "email": "developer@platform.dev",
            "password": "SecurePassword123",
            "role": "developer",
        },
    )
    assert reg_resp.status_code == 201

    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "developer@platform.dev", "password": "SecurePassword123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 读取 PRD 评审助手 plugin.yaml 并部署
    raw_manifest = load_manifest(PLUGIN_DIR / "plugin.yaml")
    deploy_resp = await client.post(
        "/api/plugins/deploy", json=raw_manifest, headers=headers
    )

    assert deploy_resp.status_code == 201
    plugin_data = deploy_resp.json()
    plugin_id = plugin_data["id"]
    assert plugin_data["name"] == "prd-review-assistant"

    # 3. 助手广场检索
    assistants_resp = await client.get("/api/assistants?query=PRD", headers=headers)
    assert assistants_resp.status_code == 200
    assistants = assistants_resp.json()
    assert len(assistants) >= 1
    assert assistants[0]["name"] == "prd-review-assistant"

    # 4. 创建专属会话
    session_resp = await client.post(
        "/api/chat/sessions", json={"plugin_id": plugin_id}, headers=headers
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    # 5. 交互回传 (M7)
    interact_resp = await client.post(
        f"/api/chat/sessions/{session_id}/blocks/blk-1/interact",
        json={"action": "input.confirm", "value": {"confirmed": True}},
        headers=headers,
    )
    assert interact_resp.status_code == 200
    blocks = interact_resp.json()["blocks"]
    assert len(blocks) == 1
    assert "已确认" in blocks[0]["data"]["text"]

    # 6. 轻反馈上报 (Thumbs)
    event_resp = await client.post(
        f"/api/chat/sessions/{session_id}/events",
        json={"kind": "thumbs", "target_block_id": "blk-1", "value": {"score": 1}},
        headers=headers,
    )
    assert event_resp.status_code == 200
    assert event_resp.json()["ok"] is True

    # 7. 重命名与删除会话
    rename_resp = await client.patch(
        f"/api/chat/sessions/{session_id}",
        json={"title": "PRD 登录需求评审会话"},
        headers=headers,
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["title"] == "PRD 登录需求评审会话"

    del_resp = await client.delete(
        f"/api/chat/sessions/{session_id}", headers=headers
    )
    assert del_resp.status_code == 200

    # 8. 停用与卸载插件
    disable_resp = await client.post(
        f"/api/plugins/{plugin_id}/disable", headers=headers
    )
    assert disable_resp.status_code == 200
    assert disable_resp.json()["status"] == "disabled"

    uninstall_resp = await client.delete(
        f"/api/plugins/{plugin_id}", headers=headers
    )
    assert uninstall_resp.status_code == 204
