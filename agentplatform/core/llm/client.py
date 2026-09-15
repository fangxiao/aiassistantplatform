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

from agentplatform.core.llm.http_client import make_http_client
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
    reasoning_content: str | None = None
    tool_call: ToolCall | None = None
    message_id: str | None = None
    error: str | None = None


class OpenAIClient:
    """针对单个或多个 LLM 端点的 OpenAI 兼容客户端，支持自动故障转移 (Failover)。"""

    def __init__(
        self,
        endpoint: LlmEndpoint,
        timeout: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
        fallback_endpoints: list[LlmEndpoint] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.base_url = endpoint.base_url.rstrip("/")
        self.api_key = get_api_key(endpoint)
        self.model = endpoint.model
        self.timeout = timeout
        self._transport = transport
        self.fallback_endpoints = fallback_endpoints or []

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式 chat.completions; 主端点遇 5xx/超时/网络异常时自动无缝降级切换到备用端点。"""
        endpoints_to_try = [self.endpoint] + self.fallback_endpoints
        last_error = None

        for idx, ep in enumerate(endpoints_to_try):
            ep_base_url = ep.base_url.rstrip("/")
            ep_api_key = get_api_key(ep)
            ep_model = ep.model

            payload: dict = {
                "model": ep_model,
                "messages": messages,
                "stream": True,
                "max_tokens": 8192,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            headers = {"Authorization": f"Bearer {ep_api_key}"}
            has_yielded = False
            client_timeout = httpx.Timeout(
                timeout=self.timeout,
                connect=15.0,
                read=self.timeout,
                write=60.0,
                pool=30.0,
            )
            try:
                async with (
                    make_http_client(timeout=client_timeout, transport=self._transport) as c,
                    c.stream(
                        "POST", f"{ep_base_url}/chat/completions", json=payload, headers=headers
                    ) as resp,
                ):
                    if resp.status_code != 200:
                        body = (await resp.aread()).decode(errors="replace")[:300]
                        err_msg = f"HTTP {resp.status_code}: {body}"
                        if idx < len(endpoints_to_try) - 1:
                            last_error = err_msg
                            continue
                        yield StreamEvent(type="error", error=err_msg)
                        return

                    message_id = ""
                    tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}
                    stream_error = None
                    reasoning_parts: list[str] = []
                    in_think_block = False

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

                        if "error" in chunk:
                            stream_error = str(chunk.get("error"))
                            break

                        message_id = chunk.get("id", message_id)
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta") or {}
                            r_text = (
                                delta.get("reasoning_content")
                                or delta.get("reasoning")
                                or delta.get("thought")
                            )
                            if r_text:
                                reasoning_parts.append(r_text)
                                has_yielded = True
                                yield StreamEvent(type="reasoning", text=r_text)
                            raw_content = delta.get("content")
                            if raw_content:
                                text_to_emit = ""
                                cur = raw_content
                                if "<think>" in cur:
                                    in_think_block = True
                                    parts = cur.split("<think>", 1)
                                    text_to_emit += parts[0]
                                    cur = parts[1]
                                if in_think_block:
                                    if "</think>" in cur:
                                        parts = cur.split("</think>", 1)
                                        reasoning_parts.append(parts[0])
                                        in_think_block = False
                                        text_to_emit += parts[1]
                                    else:
                                        reasoning_parts.append(cur)
                                else:
                                    # 去除松散的 </think> 或 <think>
                                    cur = cur.replace("</think>", "").replace("<think>", "")
                                    text_to_emit += cur

                                if text_to_emit:
                                    has_yielded = True
                                    yield StreamEvent(type="delta", text=text_to_emit)

                            for tc in delta.get("tool_calls") or []:
                                has_yielded = True
                                _merge_tool_call(tool_calls, tc)

                    if stream_error:
                        if not has_yielded and idx < len(endpoints_to_try) - 1:
                            last_error = stream_error
                            continue
                        yield StreamEvent(type="error", error=stream_error)
                        return

                    full_reasoning = "".join(reasoning_parts) if reasoning_parts else None

                    # 流结束:先发完整 tool_calls(按 index 排序),再发 done
                    for tc_idx in sorted(tool_calls):
                        tc = tool_calls[tc_idx]
                        yield StreamEvent(
                            type="tool_call",
                            tool_call=ToolCall(
                                id=tc.get("id") or f"call_{tc_idx}",
                                name=tc.get("name", ""),
                                arguments=tc.get("arguments", ""),
                            ),
                            reasoning_content=full_reasoning,
                        )
                    yield StreamEvent(
                        type="done", message_id=message_id, reasoning_content=full_reasoning
                    )
                    return

            except Exception as exc:
                if not has_yielded and idx < len(endpoints_to_try) - 1:
                    last_error = f"{type(exc).__name__}: {exc}"
                    continue
                yield StreamEvent(type="error", error=f"LLM 请求失败 ({ep_base_url}): {type(exc).__name__}: {exc}")
                return

        if last_error:
            yield StreamEvent(type="error", error=f"所有端点均不可用，最后错误: {last_error}")


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
