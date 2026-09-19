"""agent 调度循环(设计 002 §5 / 001 §core/agent)。

LLM -> tool_call -> 执行 -> 回填 -> 再推理;无 tool_call 即结束。
llm_client 注入(实现 stream 接口,见 core/llm/client.py),测试可 mock。
stream_agent 流式产出 delta / tool_call 事件(供 M6 SSE);run_agent 聚合为结果。

skill 执行嵌套一次 LLM 调用(002 §5.3 简单 skill)。
"""

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.bridge import bridge
from agentplatform.core.agent.errors import AgentLoopError
from agentplatform.core.agent.executor import execute_skill, execute_tool
from agentplatform.core.agent.messages import build_messages, build_system_prompt
from agentplatform.core.agent.tools import build_tools
from agentplatform.core.kb.search_tool import KB_SEARCH_TOOL_ID, run_kb_search
from agentplatform.core.llm.client import ToolCall
from agentplatform.core.registry.model import SkillTool, SkillToolKind
from agentplatform.core.registry.service import resolve
from agentplatform.core.agent.http_action import HTTP_ACTION_TOOL_ID, run as http_action_run
from agentplatform.core.agent.web_search import WEB_SEARCH_TOOL_ID, run as web_search_run
from agentplatform.core.memory.tool import MEMORY_TOOL_ID, run as memory_run
from agentplatform.core.workbench.todo_tool import WORKBENCH_TODO_TOOL_ID
from agentplatform.core.workbench.todo_tool import run as todo_run

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
    usage: dict | None = None  # 打磨:LLM token 用量(done 事件携带)



@dataclass(frozen=True)
class AgentResult:
    """一次 agent 运行结果。"""

    text: str
    tool_traces: list[ToolTrace]
    usage_tokens: int | None = None  # 打磨:全部轮次 token 合计


async def run_agent(
    session: AsyncSession,
    llm_client: object,
    *,
    resource_ids: list[str],
    user_message: str,
    history: list[dict] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    owner_id: str | None = None,
    allowed_kb_ids: list[uuid.UUID] | None = None,
    memories: list[str] | None = None,
) -> AgentResult:
    """聚合版调度循环(非流式,兼容旧调用)。"""
    text_parts: list[str] = []
    traces: list[ToolTrace] = []
    usage_total = 0
    async for ev in stream_agent(
        session,
        llm_client,
        resource_ids=resource_ids,
        user_message=user_message,
        history=history,
        max_iterations=max_iterations,
        owner_id=owner_id,
        allowed_kb_ids=allowed_kb_ids,
        memories=memories,
    ):
        if ev.type == "delta" and ev.text:
            text_parts.append(ev.text)
        elif ev.type == "tool_call" and ev.tool_trace is not None:
            if ev.tool_trace.result != "":
                traces.append(ev.tool_trace)
        elif ev.type == "done" and ev.usage:
            usage_total += int((ev.usage or {}).get("total_tokens") or 0)
    return AgentResult(
        text="".join(text_parts), tool_traces=traces, usage_tokens=usage_total or None
    )


def _find_resource(name: str, resources: dict[str, SkillTool]) -> SkillTool | None:
    """鲁棒解析工具/技能资源，兼容带前缀、下划线转换、点号路径、版本号后缀等全部变体。"""
    if not name:
        return None
    if name in resources:
        return resources[name]
    norm = name.replace("__", ":")
    if norm in resources:
        return resources[norm]
    bare = norm.split(":", 1)[-1].split("@", 1)[0].strip()
    if bare in resources:
        return resources[bare]
    if name.startswith("tool_"):
        candidate = f"tool:{name[5:]}"
        if candidate in resources:
            return resources[candidate]
    if name.startswith("skill_"):
        candidate = f"skill:{name[6:]}"
        if candidate in resources:
            return resources[candidate]
    dot_replaced = bare.replace(".", "_")
    if dot_replaced in resources:
        return resources[dot_replaced]
    for k, v in resources.items():
        if (
            k == bare
            or v.name == bare
            or v.name == dot_replaced
            or k.endswith(f":{bare}")
            or k.endswith(f"__{bare}")
            or bare == k.split(":", 1)[-1]
            or (v.impl_path and v.impl_path.endswith(bare))
            or (v.impl_path and v.impl_path.replace(".", "_").endswith(dot_replaced))
        ):
            return v
    return None


async def stream_agent(
    session: AsyncSession,
    llm_client: object,
    *,
    resource_ids: list[str],
    user_message: str,
    history: list[dict] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    owner_id: str | None = None,
    plugin_desc: str | None = None,
    allowed_kb_ids: list[uuid.UUID] | None = None,
    memories: list[str] | None = None,
    images: list[str] | None = None,
) -> AsyncIterator[AgentEvent]:
    """流式调度循环:显式调用编排 + 执行回填(002 §5)。

    owner_id 为资源属主(会话用户 id),用于端侧工具经浏览器隧道路由;
    为 None 或浏览器未连接时,端侧工具降级为 await_external SSE + 暂停。
    allowed_kb_ids 为知识库检索允许范围(M12,chat 侧组装,设计 008 §3.3)。
    """
    tools = await build_tools(session, resource_ids)
    resources: dict[str, SkillTool] = {}
    for rid in resource_ids:
        row = await resolve(session, rid)
        if row is not None:
            # 注册全部名称与别名形式，确保任意调用形式(如 tool:xxx, tool__xxx, xxx)均能精准命中
            resources[row.id] = row
            resources[row.id.replace(":", "__")] = row
            if ":" in row.id:
                bare = row.id.split(":", 1)[1]
                resources[bare] = row
                resources[bare.replace(":", "__")] = row
                resources[f"tool:{bare}"] = row
                resources[f"tool__{bare}"] = row
                resources[f"skill:{bare}"] = row
                resources[f"skill__{bare}"] = row
    # 资源加载完毕即提交释放事务:LLM 流式远超 idle_in_transaction_session_timeout(30s),
    # 携带空闲事务进入长流式阶段会被 PG 终止连接,导致最终结果无法落库。
    await session.commit()

    system = build_system_prompt(
        list(resources.values()), plugin_desc=plugin_desc, memories=memories
    )
    messages = build_messages(system, history, user_message, images=images)

    import asyncio
    skill_delta_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def skill_call(prompt: str) -> str:
        """简单 skill 的一次 LLM 调用(002 §5.3)。实时将 delta 注入队列以流式渲染给用户。"""
        chunks: list[str] = []
        async for e in _stream(llm_client, [{"role": "user", "content": prompt}]):
            if e.type == "delta" and e.text:
                chunks.append(e.text)
                await skill_delta_queue.put(e.text)
        return "".join(chunks)

    # M17 P1:写操作确认框积攒区(执行后由 block_meta 通道下发)
    pending_confirm_blocks: list[dict] = []

    async def execute(resource: SkillTool | None, arguments: str) -> str:
        """执行单个 tool_call,任何异常都回填为文本(让 LLM 可自纠)。"""
        if resource is None:
            return "错误:未找到该资源"
        args = _parse_args(arguments)
        try:
            if resource.id == KB_SEARCH_TOOL_ID:
                # 知识库检索:需要会话允许范围,不走通用 executor(设计 008 §3.3);
                # 打磨④:透传最近对话文本供 query 改写(指代消解)
                recent = [
                    {"role": m.get("role"), "content": m.get("content")}
                    for m in messages
                    if isinstance(m.get("content"), str)
                ][-4:]
                return await run_kb_search(session, allowed_kb_ids or [], args, history=recent)
            if resource.id == WORKBENCH_TODO_TOOL_ID:
                # 个人待办:需要会话用户上下文(M14;与 kb_search 同款特判模式)
                return await todo_run(session, owner_id or "", args)
            if resource.id == MEMORY_TOOL_ID:
                # 长期记忆:需要会话用户上下文(M15 P1)
                return await memory_run(session, owner_id or "", args)
            if resource.id == WEB_SEARCH_TOOL_ID:
                # 联网搜索:无 DB 依赖,纯网络调用(M15 P1)
                return await web_search_run(args)
            if resource.id == HTTP_ACTION_TOOL_ID:
                # 通用 HTTP 动作:白名单+SSRF 约束(M17);写操作挂起等用户确认(M17 P1)
                result = await http_action_run(args)
                try:
                    import json as _json

                    data = _json.loads(result)
                    if isinstance(data, dict) and data.get("pending"):
                        confirm_id = data.get("confirm_id", "")
                        digest = data.get("digest", "")
                        pending_confirm_blocks.append(
                            {
                                "type": "input.confirm",
                                "data": {
                                    "text": f"⚠️ 助手请求执行写操作,请确认:\n{digest}",
                                    "action": f"http_action:{confirm_id}",
                                    "confirm_text": "确认执行",
                                    "cancel_text": "取消",
                                },
                            }
                        )
                except Exception:  # noqa: BLE001  非 JSON 不处理
                    pass
                return result
            if resource.kind == SkillToolKind.tool:
                return await execute_tool(resource, args)
            return await execute_skill(resource, args, skill_call)
        except Exception as exc:  # noqa: BLE001  执行失败回填给 LLM
            return f"执行错误: {exc}"

    for _ in range(max_iterations):
        delta_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        calls: list[ToolCall] = []

        round_usage = 0
        async for e in _stream(llm_client, messages, tools):
            if e.type == "error":
                raise AgentLoopError(e.error or "LLM 调用失败")
            if e.type == "done" and e.usage:
                round_usage += int((e.usage or {}).get("total_tokens") or 0)
            elif e.type == "reasoning" and e.text:
                reasoning_chunks.append(e.text)
                yield AgentEvent(type="reasoning", text=e.text)
            elif e.type == "delta" and e.text:
                delta_chunks.append(e.text)
                yield AgentEvent(type="delta", text=e.text)
            elif e.type == "tool_call" and e.tool_call is not None:
                calls.append(e.tool_call)

        accumulated_text = "".join(delta_chunks)
        accumulated_reasoning = "".join(reasoning_chunks) if reasoning_chunks else None

        # 思考模型兜底：如果模型把文章或输出写在推理/思考流中导致正文 delta 为空，自动提取实质内容作为回复
        if not accumulated_text.strip() and accumulated_reasoning:
            import re
            content_match = re.search(
                r"(?:^|\n)(#+\s+[^\n]+|【标题】[^\n]+|<(?:section|div|p|h\d)[\s\S]*)\Z",
                accumulated_reasoning,
            )
            if content_match:
                extracted_content = content_match.group(1).strip()
                accumulated_text = extracted_content
            else:
                accumulated_text = accumulated_reasoning
            yield AgentEvent(type="delta", text=accumulated_text)

        if not calls:
            calls = _extract_text_tool_calls(accumulated_text, resources)

        if not calls:
            # 没有工具调用: 本轮对话流式生成完毕，直接退出
            break

        assistant_msg: dict = {
            "role": "assistant",
            "content": accumulated_text or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in calls
            ],
        }
        if accumulated_reasoning:
            assistant_msg["reasoning_content"] = accumulated_reasoning
        messages.append(assistant_msg)

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
                resource = _find_resource(tc.name, resources)
                norm_name = resource.id if resource else (tc.name.replace("__", ":") if "__" in tc.name else tc.name)
                if is_endpoint_resource(resource):
                    # 端侧工具:不本地执行,经桥接下发浏览器并等待结果回填
                    args = _parse_args(tc.arguments)
                    if "browser_wechat_draft" in norm_name:
                        if not args.get("html_content") or len(str(args.get("html_content", "")).strip()) < 20:
                            art_title, art_digest, art_html = _extract_article_info(history, accumulated_text)
                            if art_html:
                                args["html_content"] = art_html
                            if not args.get("title") and art_title:
                                args["title"] = art_title
                            if not args.get("digest") and art_digest:
                                args["digest"] = art_digest
                    action = resource.impl_path[len(ENDPOINT_PREFIX):]  # type: ignore[union-attr]
                    if owner_id and bridge.is_connected(owner_id):
                        progress_q: asyncio.Queue[AgentEvent] = asyncio.Queue()

                        async def _on_step(step_data: dict) -> None:
                            step_desc = (
                                step_data.get("message")
                                or step_data.get("title")
                                or step_data.get("step")
                                or str(step_data)
                            )
                            await progress_q.put(
                                AgentEvent(
                                    type="tool_call",
                                    tool_trace=ToolTrace(
                                        id=norm_name,
                                        args=args,
                                        result=f"⚡ [{step_desc}]",
                                    ),
                                    block={"type": "collaboration.step", "data": step_data},
                                )
                            )

                        # 双向隧道:route_to_endpoint 等待 TOOL_RESULT 后返回,并实时上报 step 进度
                        route_task = asyncio.create_task(
                            bridge.route_to_endpoint(
                                owner_id, action, args, call_id=tc.id, on_progress=_on_step
                            )
                        )
                        while not route_task.done():
                            try:
                                ev = await asyncio.wait_for(progress_q.get(), timeout=0.1)
                                yield ev
                            except TimeoutError:
                                continue
                        while not progress_q.empty():
                            yield progress_q.get_nowait()

                        result = await route_task
                        yield AgentEvent(
                            type="tool_call",
                            tool_trace=ToolTrace(id=norm_name, args=args, result=result),
                        )
                    else:
                        # 无浏览器连接:降级为 await_external SSE + 暂停(interact 回传),维持既有 POC
                        block = {
                            "type": "await_external",
                            "data": {
                                "action": action,
                                "tool_id": norm_name,
                                "call_id": tc.id,
                                "args": args,
                            },
                        }
                        trace = ToolTrace(
                            id=norm_name,
                            args=args,
                            result=f"端侧动作已下发({action}),等待浏览器执行结果回传。",
                        )
                        yield AgentEvent(type="tool_call", tool_trace=trace)
                        yield AgentEvent(type="await_external", block=block)
                        return
                else:
                    # 1. 自动补全空参数与 HTML 回填
                    tool_args = _parse_args(tc.arguments)
                    if "writewx_preview" in norm_name:
                        if not tool_args.get("html") or len(str(tool_args.get("html", "")).strip()) < 20:
                            extracted_h = _extract_html_fallback(accumulated_text)
                            if extracted_h:
                                tool_args["html"] = extracted_h
                        if not tool_args.get("title"):
                            tool_args["title"] = "技术长文"
                        tc = ToolCall(
                            id=tc.id,
                            name=tc.name,
                            arguments=json.dumps(tool_args, ensure_ascii=False),
                        )

                    # 1. 优先下发工具调用开始事件(通知前端立即进入执行态)
                    start_trace = ToolTrace(
                        id=norm_name, args=tool_args, result=""
                    )
                    yield AgentEvent(type="tool_call", tool_trace=start_trace)

                    # 2. 实际执行工具逻辑（若为 skill 撰写，则将内部生成内容实时流式传输给用户）
                    exec_task = asyncio.create_task(execute(resource, tc.arguments))
                    while not exec_task.done():
                        try:
                            chunk = await asyncio.wait_for(skill_delta_queue.get(), timeout=0.05)
                            if chunk:
                                yield AgentEvent(type="skill_delta", text=chunk)
                        except TimeoutError:
                            continue
                    while not skill_delta_queue.empty():
                        chunk = skill_delta_queue.get_nowait()
                        if chunk:
                            yield AgentEvent(type="skill_delta", text=chunk)

                    result = await exec_task
                    trace = ToolTrace(
                        id=norm_name, args=tool_args, result=result
                    )
                    yield AgentEvent(type="tool_call", tool_trace=trace)
                    # M17 P1:写操作确认框下发(由 execute 内积攒)
                    for confirm_block in pending_confirm_blocks:
                        yield AgentEvent(type="block_meta", block=confirm_block)
                    pending_confirm_blocks.clear()

                    # 3. 如果是预览工具，自动向前端下发文件下载/预览卡片
                    if "writewx_preview" in norm_name:
                        try:
                            res_data = json.loads(result)
                            if isinstance(res_data, dict) and res_data.get("status") == "success":
                                file_path = res_data.get("path", "")
                                filename = res_data.get("filename", "article.html")
                                yield AgentEvent(
                                    type="block_meta",
                                    block={
                                        "type": "file",
                                        "data": {
                                            "name": filename,
                                            "path": file_path,
                                            "mime": "text/html",
                                        },
                                    },
                                )
                        except Exception:
                            pass

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        # 工具执行会开启事务(如 kb_search 的检索查询);在下一轮长流式前提交释放,
        # 避免 idle-in-transaction 超时被 PG 断连,导致流结束后的消息落库失败。
        await session.commit()

    # 4. 自动落盘兜底:如果模型直接生成了 HTML 但未显式调用 preview 工具
    preview_res = next((res for rid, res in resources.items() if "preview" in rid), None)
    if preview_res:
        extracted_html = _extract_html_fallback(accumulated_text)
        if extracted_html and len(extracted_html) > 100:
            import re
            extracted_title = "微信公众号文章"
            title_patterns = [
                r"(?:\d+\.\s*)?\*{0,2}文章标题\*{0,2}[：:]\s*([^\n\r]+)",
                r"【标题】\s*([^\n\r]+)",
                r"<title>([^<]+)</title>",
                r"<h1[^>]*>([^<]+)</h1>",
                r"(?:^|\n)#\s+([^\n\r]+)",
            ]
            for p in title_patterns:
                m = re.search(p, accumulated_text, re.IGNORECASE)
                if m:
                    t = re.sub(r"[*_#`]+", "", m.group(1)).strip()
                    if t and len(t) < 80:
                        extracted_title = t
                        break

            preview_args = {"html": extracted_html, "title": extracted_title}
            prev_result_str = await execute_tool(preview_res, preview_args)
            try:
                res_data = json.loads(prev_result_str)
                if isinstance(res_data, dict) and res_data.get("status") == "success":
                    file_path = res_data.get("path", "")
                    filename = res_data.get("filename", f"{extracted_title}-公众号版.html")
                    yield AgentEvent(
                        type="block_meta",
                        block={
                            "type": "file",
                            "data": {
                                "name": filename,
                                "path": file_path,
                                "url": f"http://localhost:8000/api/files/raw?path={file_path}",
                                "mime": "text/html",
                            },
                        },
                    )
            except Exception:
                pass

    yield AgentEvent(
        type="done",
        usage={"total_tokens": round_usage} if round_usage else None,
    )



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


def _strip_tool_syntax(text: str) -> str:
    """过滤模型输出中混杂的 JSON 参数、tool_call 标记等内部调用代码。"""
    if not text:
        return ""
    import re
    # 移除 <tool_call>...</tool_call>
    t = re.sub(r"<tool_call>[\s\S]*?(?:</tool_call>|\Z)", "", text)
    # 移除 `tool:xxx`(...) 或 `skill:xxx`(...)
    t = re.sub(r"`?(?:skill|tool):[a-zA-Z0-9_-]+`?\s*\([\s\S]*?\)", "", t)
    # 移除独立代码块 ```json ... ``` 或 ``` ... ```
    t = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", t)
    # 移除纯 JSON 对象 { ... }
    t_stripped = t.strip()
    if t_stripped.startswith("{") and t_stripped.endswith("}"):
        try:
            json.loads(t_stripped)
            return ""
        except Exception:
            pass
    # 移除类似 "topic": "...", "audience": "..." 散乱参数行及内部工具调用宣告
    lines = [
        l
        for l in t.splitlines()
        if not re.search(r'^\s*"(?:topic|audience|style|length|title|tone|word_count)"\s*:', l)
        and not re.search(r"^\s*[{}]\s*$", l)
        and not re.search(r"(?:调用(?:技能|工具)|执行(?:技能|工具))\s*[`']?(?:skill|tool):", l)
        and not re.search(r"^步骤\s*\d+[\s:：].*(?:获取排版|调用)", l)
    ]
    return "\n".join(lines).strip()


def _extract_html_fallback(text: str) -> str | None:
    """从大模型生成的文本、markdown 代码块或 JSON 字符串中鲁棒提取 HTML 内容。"""
    import re
    if not text:
        return None
    # 1. 尝试匹配 ```html ... ```
    m = re.search(r"```html\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 2. 尝试从 JSON "html": "..." 中提取并反转义
    html_m = re.search(r"\"(?:html|content|html_content)\"\s*:\s*\"((?:\\.|[^\"\\])*)", text)
    if html_m:
        raw_html = html_m.group(1)
        return raw_html.replace(r"\"", "\"").replace(r"\n", "\n").replace(r"\t", "\t").replace(r"\/", "/")
    m = re.search(r"(<(?:section|div|article|html|!DOCTYPE)\s+[\s\S]*?(?:</(?:section|div|article|html)>|\Z))", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _extract_article_info(history: list[dict] | None, current_text: str) -> tuple[str, str, str]:
    """从历史消息或当前文本中提取最近一次生成的文章标题、摘要与完整 HTML。"""
    import re
    all_texts: list[str] = []
    if history:
        for h in reversed(history):
            content = h.get("content") or ""
            if "<section" in content or "```html" in content or "【标题】" in content or "文章标题" in content:
                all_texts.append(content)
    all_texts.append(current_text)

    combined = "\n\n".join(all_texts)
    html = _extract_html_fallback(combined) or ""

    title = "微信公众号文章"
    title_patterns = [
        r"(?:\d+\.\s*)?\*{0,2}文章标题\*{0,2}[：:]\s*([^\n\r]+)",
        r"(?:\d+\.\s*)?\*{0,2}标题\*{0,2}[：:]\s*([^\n\r]+)",
        r"【标题】\s*([^\n\r]+)",
        r"<h1[^>]*>([^<]+)</h1>",
        r"<title>([^<]+)</title>",
        r"(?:^|\n)#\s+([^\n\r]+)",
    ]
    for p in title_patterns:
        m = re.search(p, combined, re.IGNORECASE)
        if m:
            t = re.sub(r"[*_#`]+", "", m.group(1)).strip()
            if t and len(t) < 80:
                title = t
                break

    digest = "点击阅读全文"
    digest_patterns = [
        r"(?:\d+\.\s*)?\*{0,2}(?:文章摘要|导语摘要|摘要)\*{0,2}[：:]\s*([^\n\r]+)",
        r"【摘要】\s*([^\n\r]+)",
    ]
    for p in digest_patterns:
        m = re.search(p, combined, re.IGNORECASE)
        if m:
            d = re.sub(r"[*_#`]+", "", m.group(1)).strip()
            if d and len(d) < 200:
                digest = d
                break

    return title, digest, html


def _extract_text_tool_calls(text: str, resources: dict[str, SkillTool]) -> list[ToolCall]:
    """从模型输出的纯文本中兜底解析以 markdown code block、JSON 或函数签名格式输出的工具调用。"""
    import re
    import uuid

    from agentplatform.core.llm.client import ToolCall

    if not text:
        return []

    candidates: dict[str, str] = {"output_block": "output_block"}
    for rid in resources:
        candidates[rid] = rid
        candidates[rid.replace(":", "__")] = rid
        if ":" in rid:
            candidates[rid.split(":", 1)[1]] = rid

    extracted: list[ToolCall] = []

    # 1. 尝试匹配 `skill:xxx`({...}) 或 skill__xxx({...}) 函数调用风格文本
    fn_matches = re.findall(
        r"`?((?:skill|tool)(?::|__)[a-zA-Z0-9_-]+|output_block)`?\s*\(\s*(\{[\s\S]*?\})\s*\)", text
    )
    for raw_name, arg_str in fn_matches:
        matched_id = (
            candidates.get(raw_name)
            or candidates.get(raw_name.replace(":", "__"))
            or candidates.get(raw_name.replace("__", ":"))
        )
        if matched_id:
            try:
                # 校验是否为合法 JSON
                json.loads(arg_str)
                extracted.append(
                    ToolCall(
                        id=f"call_txt_{uuid.uuid4().hex[:8]}",
                        name=matched_id.replace(":", "__"),
                        arguments=arg_str,
                    )
                )
            except Exception:
                continue

    # 1.2 尝试匹配函数签名风格: kb_search(query="...") / tool:kb_search(query="...", top_k=3)
    # (部分模型以 Python kwargs 形式书写;仅当函数名命中已知资源时才解析,避免误伤普通文本。
    #  精确匹配优先于 1.5 的截断启发式,故命中即返回。)
    import ast as _ast

    sig_matches = re.finditer(
        r"`?\b([a-zA-Z][a-zA-Z0-9_]*(?::[a-zA-Z0-9_-]+)?)\s*\(\s*([a-zA-Z_][\w]*\s*=)", text
    )
    for m in sig_matches:
        raw_name = m.group(1)
        probe = candidates.get(raw_name) or candidates.get(raw_name.replace(":", "__")) or candidates.get(
            raw_name.replace("__", ":")
        )
        if not probe:
            continue
        # 从 kwargs 起点到配对右括号,交由 ast 安全解析字面量
        start = m.start(2)
        end = text.find(")", start)
        if end == -1:
            continue
        try:
            call = _ast.parse(f"_f({text[start:end]})").body[0].value  # type: ignore[attr-defined]
            kwargs = {kw.arg: _ast.literal_eval(kw.value) for kw in call.keywords if kw.arg}
        except Exception:
            continue
        extracted.append(
            ToolCall(
                id=f"call_txt_{uuid.uuid4().hex[:8]}",
                name=probe.replace(":", "__"),
                arguments=json.dumps(kwargs, ensure_ascii=False),
            )
        )
    if extracted:
        return extracted

    # 1.5 尝试匹配截断或未闭合的函数/工具调用: <tool_call>tool:xxx({ ... 或 `tool__xxx`({ ...
    trunc_m = re.search(
        r"(?:<tool_call>\s*)?`?((?:tool|skill)(?::|__)[a-zA-Z0-9_-]+|writewx_preview)`?\s*\(\s*\{?([\s\S]*?)(?:\)\s*(?:</tool_call>)?|\Z)",
        text,
    )
    if trunc_m:
        raw_name = trunc_m.group(1).strip()
        body = trunc_m.group(2)
        matched_id = (
            candidates.get(raw_name)
            or candidates.get(raw_name.replace(":", "__"))
            or candidates.get(raw_name.replace("__", ":"))
        )
        if matched_id:
            args_trunc: dict = {}
            html = _extract_html_fallback(body)
            if html:
                args_trunc["html"] = html
                args_trunc["html_content"] = html
            title_m = re.search(r"\"title\"\s*:\s*\"((?:\\.|[^\"\\])*)", body)
            if title_m:
                args_trunc["title"] = title_m.group(1).replace(r"\"", "\"")
            else:
                args_trunc["title"] = "公众号技术长文"
            if args_trunc:
                extracted.append(
                    ToolCall(
                        id=f"call_txt_{uuid.uuid4().hex[:8]}",
                        name=matched_id.replace(":", "__"),
                        arguments=json.dumps(args_trunc, ensure_ascii=False),
                    )
                )

    if extracted:
        return extracted

    # 2. 尝试匹配 XML / 标签调用: <function=skill:...>, <invoke name="...">, 多个连续 <tool_call> 等
    tag_matches = re.finditer(
        r"<(?:function|invoke|tool_call|action|tool)(?:\s+name=|=)[\"\x27]?([^\s\"\x27>]+)[\"\x27]?>([\s\S]*?)(?:</(?:function|invoke|tool_call|action|tool)>|$)",
        text,
        re.IGNORECASE,
    )
    for m in tag_matches:
        raw_name = m.group(1).strip()
        inner = m.group(2)
        params = re.findall(
            r"<parameter(?:\s+name=|=)[\"\x27]?([^\s\"\x27>]+)[\"\x27]?>([\s\S]*?)</parameter>",
            inner,
            re.IGNORECASE,
        )
        param_dict = {k.strip(): v.strip() for k, v in params}
        if raw_name.lower() in ("skill", "tool", "function", "action", "tool_call"):
            raw_name = param_dict.pop("name", "") or param_dict.pop("id", "") or param_dict.pop("func", "")

        # 无参数名的 <parameter>值</parameter>(部分模型风格):唯一无名参数绑定到
        # 目标函数唯一必填参数(kb_search 即 query),避免参数丢失导致调用必败。
        if not param_dict and raw_name:
            unnamed_vals = [
                m.group(2).strip()
                for m in re.finditer(r"<parameter([^>]*)>([\s\S]*?)</parameter>", inner, re.IGNORECASE)
                if "name" not in m.group(1) and m.group(2).strip()
            ]
            probe_id = candidates.get(raw_name) or candidates.get(raw_name.replace(":", "__")) or candidates.get(
                raw_name.replace("__", ":")
            )
            row = resources.get(probe_id or "")
            required: list[str] = []
            if row is not None:
                schema_params = (row.schema_ or {}).get("parameters") or row.schema_ or {}
                required = schema_params.get("required") or []
                if not required:
                    required = list((schema_params.get("properties") or {}).keys())
            if len(unnamed_vals) == 1 and required:
                param_dict[required[0]] = unnamed_vals[0]

        if raw_name:
            matched_id = (
                candidates.get(raw_name)
                or candidates.get(raw_name.replace(":", "__"))
                or candidates.get(raw_name.replace("__", ":"))
            )
            if matched_id:
                if "title" in param_dict and "topic" not in param_dict:
                    param_dict["topic"] = param_dict["title"]
                extracted.append(
                    ToolCall(
                        id=f"call_txt_{uuid.uuid4().hex[:8]}",
                        name=matched_id.replace(":", "__"),
                        arguments=json.dumps(param_dict, ensure_ascii=False),
                    )
                )

    # 3. 尝试匹配 <tool_call>skill:name\n{json}\n</tool_call> 风格
    tool_tag_matches = re.findall(
        r"<tool_call>\s*([a-zA-Z0-9_:-]+)\s*(\{[\s\S]*?\})(?:\s*</tool_call>)?",
        text,
    )
    for raw_name, arg_str in tool_tag_matches:
        matched_id = (
            candidates.get(raw_name)
            or candidates.get(raw_name.replace(":", "__"))
            or candidates.get(raw_name.replace("__", ":"))
        )
        if matched_id:
            try:
                data_obj = json.loads(arg_str)
                extracted.append(
                    ToolCall(
                        id=f"call_txt_{uuid.uuid4().hex[:8]}",
                        name=matched_id.replace(":", "__"),
                        arguments=arg_str if isinstance(data_obj, dict) else "{}",
                    )
                )
            except Exception:
                continue

    # 3.5 尝试匹配 <tool_call>{"name": "xxx", "arguments": {...}}</tool_call> 对象风格(Qwen 等)
    # 用 raw_decode 从各 <tool_call> 内的首个 { 做真实 JSON 解码:嵌套与字符串内
    # 花括号都天然正确,连续多块逐个取到。
    decoder = json.JSONDecoder()
    for m in re.finditer(r"<tool_call>\s*", text):
        brace = text.find("{", m.end())
        if brace == -1:
            continue
        try:
            data_obj, _ = decoder.raw_decode(text, brace)
        except Exception:
            continue
        if not isinstance(data_obj, dict) or "name" not in data_obj:
            continue
        raw_name = str(data_obj.get("name") or data_obj.get("function", {}).get("name") or "").strip()
        args_obj = data_obj.get("arguments", {})
        if isinstance(args_obj, str):
            try:
                args_obj = json.loads(args_obj)
            except Exception:
                args_obj = {}
        matched_id = (
            candidates.get(raw_name)
            or candidates.get(raw_name.replace(":", "__"))
            or candidates.get(raw_name.replace("__", ":"))
        )
        if matched_id:
            extracted.append(
                ToolCall(
                    id=f"call_txt_{uuid.uuid4().hex[:8]}",
                    name=matched_id.replace(":", "__"),
                    arguments=json.dumps(args_obj, ensure_ascii=False),
                )
            )

    if extracted:
        return extracted
    json_blocks = re.findall(
        r"```(?:json|tool_call|tool|function|action|python)?\s*([\s\S]*?)\s*```",
        text,
        re.IGNORECASE,
    )
    if not json_blocks:
        json_blocks = re.findall(
            r"(\[\s*\{[\s\S]*?\}\s*\]|\{\s*\"(?:type|name|function|tool|action|tool_calls)\"[\s\S]*?\})",
            text,
        )

    for blk in json_blocks:
        try:
            data = json.loads(blk.strip())
            if isinstance(data, dict) and "tool_calls" in data and isinstance(data["tool_calls"], list):
                items = data["tool_calls"]
            elif isinstance(data, list):
                items = data
            else:
                items = [data]
            for it in items:
                if isinstance(it, dict):
                    if "function" in it and isinstance(it["function"], dict):
                        fn = it["function"]
                        raw_name = fn.get("name") or fn.get("func")
                        args = fn.get("arguments") or fn.get("parameters") or fn.get("args") or {}
                    else:
                        raw_name = it.get("name") or it.get("func") or it.get("tool") or it.get("action") or it.get("function")
                        args = (
                            it.get("args")
                            or it.get("input")
                            or it.get("arguments")
                            or it.get("parameters")
                            or {}
                        )
                    if isinstance(raw_name, str):
                        matched_id = (
                            candidates.get(raw_name)
                            or candidates.get(raw_name.replace(":", "__"))
                            or candidates.get(raw_name.replace("__", ":"))
                        )
                        if matched_id:
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except Exception:
                                    pass
                            if isinstance(args, dict):
                                if "content" in args and "html" not in args:
                                    args["html"] = args["content"]
                                if "content" in args and "html_content" not in args:
                                    args["html_content"] = args["content"]
                            arg_str = json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args)
                            extracted.append(
                                ToolCall(
                                    id=f"call_txt_{uuid.uuid4().hex[:8]}",
                                    name=matched_id.replace(":", "__"),
                                    arguments=arg_str,
                                )
                            )
        except Exception:
            continue

    if extracted:
        return extracted

    # 5. 兜底策略: 如果模型输出了裸参数 JSON (无 name / tool 字段)，按参数与挂载资源的 schema 属性重合度自动推断
    raw_json_objs = re.findall(r"(\{[\s\S]*?\})", text)
    for obj_str in raw_json_objs:
        try:
            data = json.loads(obj_str.strip())
            if isinstance(data, dict) and not any(
                k in data for k in ("name", "tool", "action", "function", "tool_calls")
            ):
                data_keys = set(data.keys())
                best_id = None
                max_overlap = 0
                for rid, res in resources.items():
                    schema = getattr(res, "schema_", {}) or {}
                    props = schema.get("properties") or {}
                    schema_props = set(props.keys()) if isinstance(props, dict) else set()
                    overlap = len(data_keys & schema_props)
                    if overlap > max_overlap:
                        max_overlap = overlap
                        best_id = rid
                if best_id and max_overlap >= 1:
                    extracted.append(
                        ToolCall(
                            id=f"call_txt_{uuid.uuid4().hex[:8]}",
                            name=best_id.replace(":", "__"),
                            arguments=json.dumps(data, ensure_ascii=False),
                        )
                    )
        except Exception:
            continue

    if not extracted:
        # 6. 自然语言意图兜底: 如果模型口头承诺 "调用写作技能" / "马上调用 skill:writewx_write" / "正在调用技能" 等
        nl_match = re.search(r"(?:调用|使用|执行)\s*(?:写作技能|[`']?(?:skill:)?writewx_write[`']?)", text)
        if nl_match and any("writewx_write" in rid for rid in resources):
            target_res = next((rid for rid in resources if "writewx_write" in rid), "skill:writewx_write")
            extracted.append(
                ToolCall(
                    id=f"call_nl_{uuid.uuid4().hex[:8]}",
                    name=target_res.replace(":", "__"),
                    arguments=json.dumps({"topic": text}, ensure_ascii=False),
                )
            )

        # 7. 自然语言草稿箱注入意图兜底: 如果模型口头提到调用草稿箱注入，或声称"注入成功"，或用户指令确认注入
        nl_draft = re.search(
            r"(?:调用|使用|重新调用|执行|发起)\s*[`']?(?:tool:)?(?:browser_wechat_draft|草稿箱注入)[`']?|(?:将文章|正在将文章|开始)?注入.*微信.*草稿箱|草稿箱.*注入成功",
            text,
        )
        if nl_draft and any("browser_wechat_draft" in rid for rid in resources):
            target_res = next((rid for rid in resources if "browser_wechat_draft" in rid), "tool:browser_wechat_draft")
            extracted.append(
                ToolCall(
                    id=f"call_draft_{uuid.uuid4().hex[:8]}",
                    name=target_res.replace(":", "__"),
                    arguments="{}",
                )
            )

    return extracted

