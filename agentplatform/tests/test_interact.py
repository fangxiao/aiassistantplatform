"""交互服务与事件接口测试(M7)。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.interact.service import handle_interaction, record_event
from agentplatform.core.session.service import create_session


@pytest.mark.asyncio
async def test_handle_interaction_confirm(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="Test Session")
    await session.commit()

    blocks = await handle_interaction(
        session,
        session_id=s.id,
        block_id="block_123",
        action="input.confirm",
        value={"confirmed": True},
    )

    assert len(blocks) == 1
    assert blocks[0]["type"] == "markdown"
    assert "已确认" in blocks[0]["data"]["text"]


@pytest.mark.asyncio
async def test_record_event_thumbs(session: AsyncSession) -> None:
    s = await create_session(session, plugin_id=None, title="Test Session")
    await session.commit()

    await record_event(
        session,
        session_id=s.id,
        kind_str="thumbs",
        block_id="block_456",
        value={"up": True},
    )
