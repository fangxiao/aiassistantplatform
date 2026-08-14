"""OpenAI 兼容客户端测试(httpx.MockTransport,不发起真实请求)。"""

import json

import httpx

from agentplatform.core.llm import crypto
from agentplatform.core.llm.client import OpenAIClient
from agentplatform.core.llm.model import LlmEndpoint

BASE_URL = "https://ark.example/v3"


def _endpoint() -> LlmEndpoint:
    return LlmEndpoint(
        name="codingplan",
        base_url=BASE_URL,
        model="deepseek-v4-flash",
        api_key_enc=crypto.encrypt("sk-test"),
        is_default=False,
    )


def _sse_response(chunks: list[dict]) -> httpx.Response:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})


class TestStreamText:
    async def test_collects_deltas_and_done(self) -> None:
        chunks = [
            {"id": "msg-1", "choices": [{"index": 0, "delta": {"content": "你好"}, "finish_reason": None}]},
            {"id": "msg-1", "choices": [{"index": 0, "delta": {"content": "世界"}, "finish_reason": None}]},
            {"id": "msg-1", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        ]
        client = OpenAIClient(_endpoint(), transport=httpx.MockTransport(lambda r: _sse_response(chunks)))
        events = [e async for e in client.stream([{"role": "user", "content": "hi"}])]
        texts = "".join(e.text or "" for e in events if e.type == "delta")
        assert texts == "你好世界"
        assert any(e.type == "done" and e.message_id == "msg-1" for e in events)
        assert not any(e.type == "tool_call" for e in events)


class TestStreamToolCall:
    async def test_accumulates_tool_call(self) -> None:
        chunks = [
            {"id": "msg-2", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "tool:pdf_parse", "arguments": ""}}]}, "finish_reason": None}]},
            {"id": "msg-2", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"file":'}}]}, "finish_reason": None}]},
            {"id": "msg-2", "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": ' "a.pdf"}'}}]}, "finish_reason": "tool_calls"}]},
        ]
        client = OpenAIClient(_endpoint(), transport=httpx.MockTransport(lambda r: _sse_response(chunks)))
        events = [e async for e in client.stream([{"role": "user", "content": "parse"}])]
        tc = next((e.tool_call for e in events if e.type == "tool_call"), None)
        assert tc is not None
        assert tc.id == "call_1"
        assert tc.name == "tool:pdf_parse"
        assert json.loads(tc.arguments) == {"file": "a.pdf"}
        assert any(e.type == "done" for e in events)


class TestErrorsAndPayload:
    async def test_http_error_yields_error_event(self) -> None:
        client = OpenAIClient(_endpoint(), transport=httpx.MockTransport(lambda r: httpx.Response(401, content="Unauthorized")))
        events = [e async for e in client.stream([{"role": "user", "content": "hi"}])]
        assert events[0].type == "error"
        assert events[0].error is not None and "401" in events[0].error

    async def test_sends_tools_and_correct_url(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["payload"] = json.loads(request.content)
            return _sse_response([])

        client = OpenAIClient(_endpoint(), transport=httpx.MockTransport(handler))
        tools = [{"type": "function", "function": {"name": "tool:pdf_parse", "parameters": {}}}]
        [e async for e in client.stream([{"role": "user", "content": "x"}], tools=tools)]
        assert captured["url"] == f"{BASE_URL}/chat/completions"
        assert captured["payload"]["tools"] == tools
        assert captured["payload"]["model"] == "deepseek-v4-flash"
