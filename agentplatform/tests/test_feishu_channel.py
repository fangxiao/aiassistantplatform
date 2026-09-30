"""飞书通道测试(M22,需求 012):会话映射、命令、文本处理。

不连真实飞书:事件消息体与回复函数以假对象/闭包替代,验证桥接逻辑。
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.channel import feishu
from agentplatform.core.channel.model import ChannelSession
from agentplatform.core.message.model import MessageRole
from agentplatform.core.message.service import list_messages
from agentplatform.core.session.service import create_session


@pytest.mark.asyncio
async def test_ensure_session_binds_and_reuses(session: AsyncSession) -> None:
    """同一 chat_id 复用同一平台会话;绑定行幂等。"""
    chat_id = "oc_test_chat_1"
    sid1 = await feishu._ensure_session_id(session, chat_id)
    sid2 = await feishu._ensure_session_id(session, chat_id)
    assert sid1 == sid2

    rows = (
        await session.scalars(
            __import__("sqlalchemy").select(ChannelSession).where(
                ChannelSession.channel == "feishu",
                ChannelSession.chat_id == chat_id,
            )
        )
    ).all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reset_binding_creates_new_session(session: AsyncSession) -> None:
    """重置后下次消息开新会话(上下文清零,A3)。"""
    chat_id = "oc_test_chat_2"
    sid1 = await feishu._ensure_session_id(session, chat_id)
    await feishu._reset_binding(session, chat_id)
    sid2 = await feishu._ensure_session_id(session, chat_id)
    assert sid1 != sid2


@pytest.mark.asyncio
async def test_process_text_runs_agent_and_replies(session: AsyncSession, monkeypatch) -> None:
    """文本消息走 agent 管线并回复(agent 以假事件流替换)。"""
    from agentplatform.core.agent.loop import AgentEvent

    chat_id = "oc_test_chat_3"
    sid = await feishu._ensure_session_id(session, chat_id)

    async def fake_stream(s, session_id, user_message, **kw):
        assert session_id == sid
        assert user_message == "你好"
        yield AgentEvent(type="delta", text="回复正文")
        yield AgentEvent(type="block_meta", block={"type": "table", "data": {}})

    monkeypatch.setattr("agentplatform.core.chat.service.agent_stream_for_session", fake_stream)
    # _process 内部经 SessionLocal 开新会话——重定向到测试引擎
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from agentplatform.core.db import session as db_session_mod

    monkeypatch.setattr(
        db_session_mod,
        "SessionLocal",
        async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False),
    )

    replies: list[str] = []

    async def reply_fn(message_id, text):
        replies.append(text)

    await feishu._process("om_1", chat_id, "你好", reply_fn)

    assert len(replies) == 1
    assert "回复正文" in replies[0]
    assert "1 个富交互组件" in replies[0]
    # 用户消息落库由真实 agent_stream_for_session 负责(fake 流替换,此处不验)


@pytest.mark.asyncio
async def test_process_reset_command(session: AsyncSession, monkeypatch) -> None:
    chat_id = "oc_test_chat_4"
    await feishu._ensure_session_id(session, chat_id)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from agentplatform.core.db import session as db_session_mod

    monkeypatch.setattr(
        db_session_mod,
        "SessionLocal",
        async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    replies: list[str] = []

    async def reply_fn(message_id, text):
        replies.append(text)

    await feishu._process("om_2", chat_id, "/重置", reply_fn)
    assert "新会话" in replies[0]
    # 绑定已清:下次 ensure 生成新会话
    rows = (
        await session.scalars(
            __import__("sqlalchemy").select(ChannelSession).where(
                ChannelSession.chat_id == chat_id
            )
        )
    ).all()
    assert list(rows) == []


def test_extract_text_only_text_type() -> None:
    msg = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                message_type="text",
                content='{"text":"你好"}',
            )
        )
    )
    assert feishu._extract_text(msg) == "你好"
    img = SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(message_type="image", content="{}")
        )
    )
    assert feishu._extract_text(img) is None


def test_reply_text_truncates_and_notes_blocks() -> None:
    out = feishu._reply_text("", 2)
    assert "未返回文本内容" in out and "2 个富交互组件" in out
    long = feishu._reply_text("x" * 70000, 0)
    assert len(long) <= 60000


@pytest.mark.asyncio
async def test_switch_and_list_commands(session: AsyncSession, monkeypatch) -> None:
    """/助手列表 与 /切换:列出可用助手;切换即换绑新插件会话。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from agentplatform.core.db import session as db_session_mod
    from agentplatform.core.plugin.model import (
        Plugin,
        PluginReviewStatus,
        PluginStatus,
    )

    monkeypatch.setattr(
        db_session_mod,
        "SessionLocal",
        async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    p = Plugin(
        name="feishu_test_plugin",
        version="0.1.0",
        manifest={"name": "feishu_test_plugin", "description": "测试助手"},
        status=PluginStatus.active,
        review_status=PluginReviewStatus.approved,
    )
    session.add(p)
    await session.commit()

    # /助手列表
    listing = await feishu._list_plugins()
    assert "feishu_test_plugin" in listing

    # /切换
    chat_id = "oc_test_switch"
    msg = await feishu._switch_plugin(session, chat_id, "feishu_test_plugin")
    assert "已切换" in msg
    sid = await feishu._bound_session_id(session, chat_id)
    assert sid is not None
    # 未知助手
    msg2 = await feishu._switch_plugin(session, chat_id, "no_such")
    assert "未找到" in msg2
