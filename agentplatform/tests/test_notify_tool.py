"""tool:notify_user 主动触达工具测试(20261015 方案 B)。

SessionLocal 重定向到测试引擎(同 test_chat_checkpoint 模式);通道数据落测试库。"""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentplatform.core.agent.notify_tool import NOTIFY_HOURLY_LIMIT, run
import importlib

# core.db.engine 被 __init__ 的同名属性遮蔽,须经 importlib 取模块本体
_ENGINE_MOD = importlib.import_module("agentplatform.core.db.engine")
from agentplatform.core.notify.model import NotificationChannel


@pytest.fixture
async def patched_sessionlocal(session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        _ENGINE_MOD,
        "SessionLocal",
        async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    return session


async def _add_channel(session: AsyncSession, user_id: str, name: str) -> None:
    session.add(
        NotificationChannel(user_id=user_id, name=name, type="webhook", config={"url": "http://hook.test/x"})
    )
    await session.commit()


@pytest.mark.asyncio
async def test_no_channels_guides_user(session: AsyncSession, patched_sessionlocal) -> None:
    out = json.loads(
        await run({"title": "情报", "message": "智谱周末送 1 亿 token"}, user_id="u-none")
    )
    assert out["ok"] is False
    assert "未配置" in out["error"]


@pytest.mark.asyncio
async def test_requires_user_and_fields(patched_sessionlocal) -> None:
    no_user = json.loads(await run({"title": "t", "message": "m"}, user_id=None))
    assert no_user["ok"] is False
    no_fields = json.loads(await run({"title": "", "message": ""}, user_id="u1"))
    assert no_fields["ok"] is False


@pytest.mark.asyncio
async def test_pushes_to_user_channels_only(
    session: AsyncSession, patched_sessionlocal, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentplatform.core.notify import service as notify_service

    await _add_channel(session, "u-own", "我的飞书")
    # 平台级通道(user_id null)对所有用户可用
    session.add(
        NotificationChannel(user_id=None, name="平台 webhook", type="webhook", config={"url": "http://hook.test/p"})
    )
    # 他人的通道不可用
    await _add_channel(session, "u-other", "别人的通道")
    await session.commit()

    sent: list[str] = []

    async def fake_deliver(channel, text):
        sent.append(f"{channel.name}:{text[:12]}")
        return True

    monkeypatch.setattr(notify_service, "deliver", fake_deliver)
    out = json.loads(
        await run({"title": "限时情报", "message": "智谱周末送 1 亿 token", "level": "alert"}, user_id="u-own")
    )
    assert out["ok"] is True and out["sent"] == 2  # 自己的 + 平台级,不含他人
    assert any(s.startswith("我的飞书:[ALERT] 限时情报") for s in sent)


@pytest.mark.asyncio
async def test_hourly_rate_limit(
    session: AsyncSession, patched_sessionlocal, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agentplatform.core.notify import service as notify_service

    async def fake_deliver(channel, text):
        return True

    monkeypatch.setattr(notify_service, "deliver", fake_deliver)
    await _add_channel(session, "u-spam", "c1")
    await session.commit()
    results = [json.loads(await run({"title": "t", "message": "m"}, user_id="u-spam")) for _ in range(NOTIFY_HOURLY_LIMIT + 1)]
    assert all(r["ok"] for r in results[:NOTIFY_HOURLY_LIMIT])
    assert results[-1]["ok"] is False and "上限" in results[-1]["error"]
