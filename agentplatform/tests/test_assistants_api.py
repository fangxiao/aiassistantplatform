"""助手广场 API 测试(M8.2)。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.plugin.loader import deploy_plugin
from agentplatform.core.plugin.manifest import PluginManifest


@pytest.fixture(autouse=True)
def _review_required(monkeypatch):
    """本文件测试审批制(ADR 0008)行为:恢复 plugin_review_required=True
    (20260930 起试用默认免审,生产语义仍需守护)。"""
    monkeypatch.setattr("agentplatform.config.settings.plugin_review_required", True)



@pytest.mark.asyncio
async def test_assistants_list_empty(client: AsyncClient) -> None:
    res = await client.get("/api/assistants")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_assistants_workflow(
    client: AsyncClient, session: AsyncSession
) -> None:

    manifest = PluginManifest(
        name="test-assistant",
        display_name="智能测试助理",
        version="1.0.0",
        description="A helpful test assistant",
        author="Developer",
        model="gpt-4o",
        depends_on=[],
        skills=[],
        tools=[],
    )
    plugin = await deploy_plugin(session, manifest)
    await session.commit()

    # ADR 0008:部署默认 pending_review,未过审不出现在广场
    res = await client.get("/api/assistants")
    assert res.status_code == 200
    assert not any(a["name"] == "test-assistant" for a in res.json())

    from agentplatform.core.plugin.loader import set_review
    from agentplatform.core.plugin.model import PluginReviewStatus

    await set_review(session, plugin, PluginReviewStatus.approved, "admin")
    await session.commit()

    res = await client.get("/api/assistants")
    assert res.status_code == 200
    data = res.json()
    assert any(a["name"] == "test-assistant" and a["display_name"] == "智能测试助理" for a in data)

    # Search filter by description
    search_res = await client.get("/api/assistants?query=helpful")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data) >= 1
    assert search_data[0]["name"] == "test-assistant"

    # Search filter by display_name
    search_cn = await client.get("/api/assistants?query=智能测试")
    assert search_cn.status_code == 200
    search_cn_data = search_cn.json()
    assert len(search_cn_data) >= 1
    assert search_cn_data[0]["name"] == "test-assistant"
    assert search_cn_data[0]["display_name"] == "智能测试助理"

