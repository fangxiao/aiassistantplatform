"""助手广场 API 测试(M8.2)。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.plugin.loader import deploy_plugin
from agentplatform.core.plugin.manifest import PluginManifest


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
        version="1.0.0",
        description="A helpful test assistant",
        author="Developer",
        model="gpt-4o",
        depends_on=[],
        skills=[],
        tools=[],
    )
    await deploy_plugin(session, manifest)
    await session.commit()

    res = await client.get("/api/assistants")
    assert res.status_code == 200
    data = res.json()
    assert any(a["name"] == "test-assistant" for a in data)

    # Search filter
    search_res = await client.get("/api/assistants?query=helpful")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data) >= 1
    assert search_data[0]["name"] == "test-assistant"

