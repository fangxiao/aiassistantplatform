"""agent 调度循环(设计 002 §5 / 001 §core/agent)。

LLM -> tool_call -> 执行 -> 回填 -> 再推理;无 tool_call 即结束。
llm_client 注入(实现 stream 接口,见 core/llm/client.py),测试可 mock。
stream_agent 流式产出 delta / tool_call 事件(供 M6 SSE);run_agent 聚合为结果。

skill 执行嵌套一次 LLM 调用(002 §5.3 简单 skill)。
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.bridge import bridge
from agentplatform.core.agent.errors import AgentLoopError
from agentplatform.core.agent.executor import execute_skill, execute_tool
from agentplatform.core.agent.messages import build_messages, build_system_prompt
from agentplatform.core.agent.tools import build_tools
from agentplatform.core.registry.model import SkillTool, SkillToolKind
from agentplatform.core.registry.service import resolve

MAX_ITERATIONS = 6

# 端侧工具标记:impl_path 以该前缀开头表示"非本地执行,下发到端侧(浏览器/扩展)等待结果回传"
ENDPOINT_PREFIX = "endpoint:"


def is_endpoint_resource(resource: SkillTool | None) -> bool:
    """判断资源是否为端侧工具(endpoint 路由,不本地执行)。"""
    return resource is not None and (resource.impl_path or "").startswith(ENDPOINT_PREFIX)


@dataclass(frozen=True)
class ToolTrace:
    """一次 tool_call 的执行记录。"""

    id: str
    args: dict
    result: str


@dataclass(frozen=True)
class AgentEvent:
    """流式 agent 事件(供 M6/M7 SSE)。"""

    type: str  # delta | tool_call | block_meta | await_external | done
    text: str | None = None
    tool_trace: ToolTrace | None = None
    block: dict | None = None



@dataclass(frozen=True)
class AgentResult:
    """一次 agent 运行结果。"""

    text: str
    tool_traces: list[ToolTrace]


async def run_agent(
    session: AsyncSession,
    llm_client: object,
    *,
    resource_ids: list[str],
    user_message: str,
    history: list[dict] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    owner_id: str | None = None,
) -> AgentResult:
    """聚合版调度循环(非流式,兼容旧调用)。"""
    text_parts: list[str] = []
    traces: list[ToolTrace] = []
    async for ev in stream_agent(
        session,
        llm_client,
        resource_ids=resource_ids,
        user_message=user_message,
        history=history,
        max_iterations=max_iterations,
        owner_id=owner_id,
    ):
        if ev.type == "delta" and ev.text:
            text_parts.append(ev.text)
        elif ev.type == "tool_call" and ev.tool_trace is not None:
            traces.append(ev.tool_trace)
    return AgentResult(text="".join(text_parts), tool_traces=traces)


async def stream_agent(
    session: AsyncSession,
    llm_client: object,
    *,
    resource_ids: list[str],
    user_message: str,
    history: list[dict] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    owner_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """流式调度循环:显式调用编排 + 执行回填(002 §5)。

    owner_id 为资源属主(会话用户 id),用于端侧工具经浏览器隧道路由;
    为 None 或浏览器未连接时,端侧工具降级为 await_external SSE + 暂停。
    """
    tools = await build_tools(session, resource_ids)
    resources: dict[str, SkillTool] = {}
    for rid in resource_ids:
        row = await resolve(session, rid)
        if row is not None:
            resources[row.id] = row
    # 资源加载完毕即提交释放事务:LLM 流式远超 idle_in_transaction_session_timeout(30s),
    # 携带空闲事务进入长流式阶段会被 PG 终止连接,导致最终结果无法落库。
    await session.commit()

    system = build_system_prompt(list(resources.values()))
    messages = build_messages(system, history, user_message)

    async def skill_call(prompt: str) -> str:
        """简单 skill 的一次 LLM 调用(002 §5.3)。"""
        events = [e async for e in _stream(llm_client, [{"role": "user", "content": prompt}])]
        return "".join(e.text or "" for e in events if e.type == "delta")

    async def execute(resource: SkillTool | None, arguments: str) -> str:
        """执行单个 tool_call,任何异常都回填为文本(让 LLM 可自纠)。"""
        if resource is None:
            return "错误:未找到该资源"
        args = _parse_args(arguments)
        try:
            if resource.kind == SkillToolKind.tool:
                return await execute_tool(resource, args)
            return await execute_skill(resource, args, skill_call)
        except Exception as exc:  # noqa: BLE001  执行失败回填给 LLM
            return f"执行错误: {exc}"

    for _ in range(max_iterations):
        events = [e async for e in _stream(llm_client, messages, tools)]
        error = next((e for e in events if e.type == "error"), None)
        if error is not None:
            raise AgentLoopError(error.error or "LLM 调用失败")
        for e in events:
            if e.type == "delta" and e.text:
                yield AgentEvent(type="delta", text=e.text)
        calls = [e.tool_call for e in events if e.type == "tool_call"]
        if not calls:
            break
        for tc in calls:
            if tc.name == "output_block":
                block_data = _parse_args(tc.arguments)
                trace = ToolTrace(
                    id="output_block",
                    args=block_data,
                    result="ContentBlock 已在客户端成功呈现。",
                )
                yield AgentEvent(type="tool_call", tool_trace=trace)
                yield AgentEvent(type="block_meta", block=block_data)
                result = "ContentBlock 已在客户端成功呈现。"
            else:
                resource = resources.get(tc.name)
                if is_endpoint_resource(resource):
                    # 端侧工具:不本地执行,经桥接下发浏览器并等待结果回填
                    args = _parse_args(tc.arguments)
                    action = resource.impl_path[len(ENDPOINT_PREFIX):]  # type: ignore[union-attr]
                    if owner_id and bridge.is_connected(owner_id):
                        # 双向隧道:route_to_endpoint 等待 TOOL_RESULT 后返回(阻塞于同事件循环)
                        result = await bridge.route_to_endpoint(
                            owner_id, action, args, call_id=tc.id
                        )
                        yield AgentEvent(
                            type="tool_call",
                            tool_trace=ToolTrace(id=tc.name, args=args, result=result),
                        )
                    else:
                        # 无浏览器连接:降级为 await_external SSE + 暂停(interact 回传),维持既有 POC
                        block = {
                            "type": "await_external",
                            "data": {
                                "action": action,
                                "tool_id": tc.name,
                                "call_id": tc.id,
                                "args": args,
                            },
                        }
                        trace = ToolTrace(
                            id=tc.name,
                            args=args,
                            result=f"端侧动作已下发({action}),等待浏览器执行结果回传。",
                        )
                        yield AgentEvent(type="tool_call", tool_trace=trace)
                        yield AgentEvent(type="await_external", block=block)
                        return
                else:
                    result = await execute(resource, tc.arguments)
                    trace = ToolTrace(
                        id=tc.name, args=_parse_args(tc.arguments), result=result
                    )
                    yield AgentEvent(type="tool_call", tool_trace=trace)
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                    ],
                }
            )
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    yield AgentEvent(type="done")



def _parse_args(arguments: str) -> dict:
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}


def _stream(
    llm_client: object, messages: list[dict], tools: list[dict] | None = None
) -> AsyncIterator:
    """适配:客户端 stream(messages, tools) 的鸭子接口。"""
    return llm_client.stream(messages, tools)  # type: ignore[attr-defined]
