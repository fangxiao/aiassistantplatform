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
async def test_handle_interaction_form_custom_action(session: AsyncSession) -> None:
    """自定义 action 名的表单提交同样走表单分支(20260929 挂起缺陷回归)。

    此前仅按命名约定(input.form / *form_submit)匹配,自定义名落入 fallback:
    表单值被静默丢弃、前端不触发续跑,表现为"提交后无响应"。
    现以 value 结构(fields 数组)为准。
    """
    s = await create_session(session, plugin_id=None, title="Test Session")
    await session.commit()

    blocks = await handle_interaction(
        session,
        session_id=s.id,
        block_id="block_form",
        action="study_intake_submit",  # 自定义名,不以 form_submit 结尾
        value={"fields": [{"id": "topic", "label": "主题", "value": "中秋"}]},
    )

    # 不再落入通用 fallback("已接收交互指令"),而是表单回执
    assert len(blocks) == 1
    assert blocks[0]["type"] == "markdown"
    assert "表单已提交" in blocks[0]["data"]["text"]


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
