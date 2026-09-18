"""多模态输入测试(设计 012):schema 校验/消息块/多部分 content/模型路由。"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.messages import build_messages
from agentplatform.core.message.service import save_user_message

TINY_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class TestBuildMessages:
    def test_images_multi_part_content(self) -> None:
        """含图消息:最新 user content 转多部分(text + image_url)。"""
        msgs = build_messages(None, [], "这是什么", images=[TINY_PNG])
        assert len(msgs) == 1 and msgs[0]["role"] == "user"
        parts = msgs[0]["content"]
        assert parts[0] == {"type": "text", "text": "这是什么"}
        assert parts[1]["type"] == "image_url"
        assert parts[1]["image_url"]["url"] == TINY_PNG

    def test_images_without_text(self) -> None:
        msgs = build_messages(None, [], "", images=[TINY_PNG])
        assert msgs[0]["content"][0]["text"] == "请看这些图片"

    def test_no_images_stays_plain(self) -> None:
        msgs = build_messages(None, [], "纯文本")
        assert msgs[0]["content"] == "纯文本"

    def test_history_unaffected(self) -> None:
        """历史不含图(设计取舍:base64 不进后续上下文)。"""
        msgs = build_messages(None, [{"role": "user", "content": "前文"}], "带图问", images=[TINY_PNG])
        assert msgs[0]["content"] == "前文"
        assert isinstance(msgs[1]["content"], list)


class TestSaveUserMessage:
    async def _make_session(self, session: AsyncSession) -> uuid.UUID:
        from agentplatform.core.session.service import create_session

        s = await create_session(session, plugin_id=None)
        return s.id

    async def test_blocks_with_images(self, session: AsyncSession) -> None:
        sid = await self._make_session(session)
        msg = await save_user_message(session, sid, "看这张图", images=[TINY_PNG])
        types = [b["type"] for b in msg.blocks]
        assert types == ["markdown", "image"]
        assert msg.blocks[1]["data"]["url"] == TINY_PNG

    async def test_image_only_message(self, session: AsyncSession) -> None:
        sid = await self._make_session(session)
        msg = await save_user_message(session, sid, "", images=[TINY_PNG])
        assert [b["type"] for b in msg.blocks] == ["image"]


@pytest.mark.asyncio
class TestSendImageValidation:
    async def test_reject_non_image_data(self, client: AsyncClient) -> None:
        sid = (await client.post("/api/chat/sessions", json={})).json()["id"]
        r = await client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"content": "x", "images": ["data:text/html;base64,PGI+"]},
        )
        assert r.status_code == 422

    async def test_reject_oversize(self, client: AsyncClient) -> None:
        import base64

        big = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
        sid = (await client.post("/api/chat/sessions", json={})).json()["id"]
        r = await client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"content": "x", "images": [f"data:image/png;base64,{big}"]},
        )
        assert r.status_code == 422

    async def test_accept_valid_image_sse(self, client: AsyncClient) -> None:
        sid = (await client.post("/api/chat/sessions", json={})).json()["id"]
        r = await client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"content": "这是什么", "images": [TINY_PNG]},
        )
        assert r.status_code == 200
        assert "event:" in r.text  # SSE 流
