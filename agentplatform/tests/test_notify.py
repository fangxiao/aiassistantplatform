"""通知出口测试(M34):微信推送格式(Server酱/pushplus)与任务 webhook 分派。"""

import pytest

from agentplatform.core.notify import service as notify_service


class TestServerchanPayload:
    def test_title_is_first_line(self) -> None:
        p = notify_service.serverchan_payload("⏰ 每日单词\n\n1. ambiguous adj. 模糊")
        assert p["title"] == "⏰ 每日单词"
        assert "ambiguous" in p["desp"]

    def test_title_clamped_to_32(self) -> None:
        p = notify_service.serverchan_payload("一" * 60 + "\n正文")
        assert len(p["title"]) == 32
        assert "正文" in p["desp"]

    def test_single_line_text(self) -> None:
        p = notify_service.serverchan_payload("只有一行")
        assert p["title"] == "只有一行"
        assert p["desp"] == "只有一行"


class TestPushplusPayload:
    def test_shape(self) -> None:
        p = notify_service.pushplus_payload("每日一句\n\nKeep going.", token="abc123")
        assert p["token"] == "abc123"
        assert p["title"] == "每日一句"
        assert p["template"] == "txt"

    def test_title_clamped_to_100(self) -> None:
        p = notify_service.pushplus_payload("一" * 200, token="t")
        assert len(p["title"]) == 100


class TestSendTaskWebhook:
    """按消息格式分派:serverchan 走表单,pushplus 从 URL 取 token,raw 保持旧契约。"""

    async def _capture(self, monkeypatch) -> tuple[list, list]:
        calls_json: list = []
        calls_form: list = []

        async def fake_json(url, payload):
            calls_json.append((url, payload))
            return True

        async def fake_form(url, data):
            calls_form.append((url, data))
            return True

        monkeypatch.setattr(notify_service, "send_webhook", fake_json)
        monkeypatch.setattr(notify_service, "send_form", fake_form)
        return calls_json, calls_form

    @pytest.mark.asyncio
    async def test_serverchan_uses_form(self, monkeypatch) -> None:
        calls_json, calls_form = await self._capture(monkeypatch)
        ok = await notify_service.send_task_webhook(
            "https://sctapi.ftqq.com/KEY.send", "serverchan", "标题行\n正文", "t"
        )
        assert ok is True and not calls_json
        assert calls_form[0][0].endswith("/KEY.send")
        assert calls_form[0][1]["title"] == "标题行"

    @pytest.mark.asyncio
    async def test_pushplus_token_from_query(self, monkeypatch) -> None:
        calls_json, _ = await self._capture(monkeypatch)
        ok = await notify_service.send_task_webhook(
            "http://www.pushplus.plus/send?token=tok1", "pushplus", "标题\n正文", "t"
        )
        assert ok is True
        assert calls_json[0][1]["token"] == "tok1"
        assert calls_json[0][1]["title"] == "标题"

    @pytest.mark.asyncio
    async def test_pushplus_missing_token_fails(self, monkeypatch) -> None:
        calls_json, calls_form = await self._capture(monkeypatch)
        ok = await notify_service.send_task_webhook(
            "http://www.pushplus.plus/send", "pushplus", "x", "t"
        )
        assert ok is False and not calls_json and not calls_form

    @pytest.mark.asyncio
    async def test_feishu_unchanged(self, monkeypatch) -> None:
        calls_json, calls_form = await self._capture(monkeypatch)
        await notify_service.send_task_webhook("https://o.feishu/hook", "feishu", "hi", "t")
        assert calls_json[0][1] == {"msg_type": "text", "content": {"text": "hi"}}
        assert not calls_form

    @pytest.mark.asyncio
    async def test_empty_kind_keeps_raw_contract(self, monkeypatch) -> None:
        """存量任务无 webhook_payload 字段 → 维持 {task, output} 旧格式。"""
        calls_json, _ = await self._capture(monkeypatch)
        await notify_service.send_task_webhook("https://x/hook", "", "产出", "我的任务")
        assert calls_json[0][1] == {"task": "我的任务", "output": "产出"}
