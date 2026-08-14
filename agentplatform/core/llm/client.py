"""OpenAI 兼容客户端(设计 001 §LLM 网关 / 002 §5 显式调用协议)。

httpx 实现 chat/completions 流式转发(SSE)。MVP 支持:
- messages / tools(function-calling,供 M5 显式调用编排)
- stream=True:迭代产出增量事件(delta / tool_call / done / error)

transport 参数供测试注入 httpx.MockTransport,不发起真实请求。
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from agentplatform.core.llm.model import LlmEndpoint
from agentplatform.core.llm.service import get_api_key


@dataclass(frozen=True)
class ToolCall:
    """完整的一次工具调用(流结束后由增量片段拼装)。"""

    id: str
    name: str
    arguments: str  # JSON 字符串,由执行器解析


@dataclass(frozen=True)
class StreamEvent:
    """流式增量事件。"""

    type: str  # delta | tool_call | done | error
    text: str | None = None
    tool_call: ToolCall | None = None
    message_id: str | None = None
    error: str | None = None


class OpenAIClient:
    """针对单个 LLM 端点的 OpenAI 兼容客户端。"""

    def __init__(
        self,
        endpoint: LlmEndpoint,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = endpoint.base_url.rstrip("/")
        self.api_key = get_api_key(endpoint)
        self.model = endpoint.model
        self.timeout = timeout
        self._transport = transport

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式 chat.completions;产出 delta / tool_call / done / error 事件。"""
        payload: dict = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools

        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with (
            httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as c,
            c.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as resp,
        ):
            if resp.status_code != 200:
                body = (await resp.aread()).decode(errors="replace")[:300]
                yield StreamEvent(type="error", error=f"HTTP {resp.status_code}: {body}")
                return

            message_id = ""
            tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                message_id = chunk.get("id", message_id)
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        yield StreamEvent(type="delta", text=delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        _merge_tool_call(tool_calls, tc)

            # 流结束:先发完整 tool_calls(按 index 排序),再发 done
            for idx in sorted(tool_calls):
                tc = tool_calls[idx]
                yield StreamEvent(
                    type="tool_call",
                    tool_call=ToolCall(
                        id=tc.get("id") or f"call_{idx}",
                        name=tc.get("name", ""),
                        arguments=tc.get("arguments", ""),
                    ),
                )
            yield StreamEvent(type="done", message_id=message_id)


def _merge_tool_call(acc: dict[int, dict], delta: dict) -> None:
    """把增量 tool_call 片段并入按 index 的累积字典。"""
    idx = delta.get("index", 0)
    entry = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
    if delta.get("id"):
        entry["id"] = delta["id"]
    fn = delta.get("function") or {}
    if fn.get("name"):
        entry["name"] += fn["name"]
    if fn.get("arguments"):
        entry["arguments"] += fn["arguments"]
