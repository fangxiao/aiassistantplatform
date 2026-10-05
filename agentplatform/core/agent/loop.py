"""agent 调度循环(设计 002 §5 / 001 §core/agent)。

LLM -> tool_call -> 执行 -> 回填 -> 再推理;无 tool_call 即结束。
llm_client 注入(实现 stream 接口,见 core/llm/client.py),测试可 mock。
stream_agent 流式产出 delta / tool_call 事件(供 M6 SSE);run_agent 聚合为结果。

skill 执行嵌套一次 LLM 调用(002 §5.3 简单 skill)。
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.agent.bridge import bridge
from agentplatform.core.agent.dispatch import (  # noqa: F401  P2.4 迁出,兼容既有导入点
    _extract_text_tool_calls,
    _find_resource,
    _parse_args,
)
from agentplatform.core.agent.errors import AgentLoopError
from agentplatform.core.agent.executor import execute_skill, execute_tool
from agentplatform.core.agent.html_render import HTML_RENDER_TOOL_ID
from agentplatform.core.agent.html_render import run as html_render_run
from agentplatform.core.agent.http_action import HTTP_ACTION_TOOL_ID
from agentplatform.core.agent.http_action import run as http_action_run
from agentplatform.core.agent.image_gen import IMAGE_GEN_TOOL_ID
from agentplatform.core.agent.image_gen import run as image_gen_run
from agentplatform.core.agent.messages import build_messages, build_system_prompt
from agentplatform.core.agent.tools import build_tools
from agentplatform.core.agent.web_search import WEB_SEARCH_TOOL_ID
from agentplatform.core.agent.web_search import run as web_search_run
from agentplatform.core.kb.search_tool import KB_SEARCH_TOOL_ID, run_kb_search
from agentplatform.core.llm.client import ToolCall
from agentplatform.core.memory.tool import MEMORY_TOOL_ID
from agentplatform.core.memory.tool import run as memory_run
from agentplatform.core.registry.model import SkillTool, SkillToolKind
from agentplatform.core.registry.service import resolve
from agentplatform.core.workbench.todo_tool import WORKBENCH_TODO_TOOL_ID
from agentplatform.core.workbench.todo_tool import run as todo_run

MAX_ITERATIONS = 6


def _log_orchestration(required: set, tools: set, skills: set, missing: set) -> None:
    """T18.3 评估日志:每次终答校验落一行 JSON(~/.agentplatform/orchestration.log)。

    双方可观测:writewx 验收需要核对"机制是否触发/为何未触发"——
    executed_source 为空即"模型未调用任何带声明的资源"形态。
    """
    import json as _json
    import time as _time

    try:
        from pathlib import Path as _P

        f = _P.home() / ".agentplatform" / "orchestration.log"
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("a", encoding="utf-8") as fh:
            fh.write(_json.dumps({
                "ts": _time.strftime("%Y-%m-%dT%H:%M:%S"),
                "required": sorted(required),
                "executed_tools": sorted(tools),
                "executed_skills": sorted(skills),
                "missing": sorted(missing),
            }, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001  日志失败不影响主流程
        pass


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
    display_name: str | None = None,
    chat_session_id: str | None = None,
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
        display_name=display_name,
        chat_session_id=chat_session_id,
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






async def _drain_until_done(task: asyncio.Task, q: asyncio.Queue):
    """消费 q 直至 task 结束再排空残余(M21 P2.5:取代 0.05s/0.1s wait_for 轮询)。

    asyncio.wait 并发等待队列与任务,零轮询间隔;任务异常由调用方 await task
    处理(行为与原轮询一致)。队列 get future 在任务先完成时取消,不丢失已入队项
    (残余经 empty() 排空)。
    """
    get_fut: asyncio.Future | None = None
    try:
        while True:
            if get_fut is None:
                get_fut = asyncio.ensure_future(q.get())
            done, _ = await asyncio.wait(
                {task, get_fut}, return_when=asyncio.FIRST_COMPLETED
            )
            if get_fut in done:
                yield get_fut.result()
                get_fut = None
            if task in done:
                break
    finally:
        if get_fut is not None and not get_fut.done():
            get_fut.cancel()
        while not q.empty():
            yield q.get_nowait()

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
    display_name: str | None = None,
    chat_session_id: str | None = None,
) -> AsyncIterator[AgentEvent]:
    """流式调度循环:显式调用编排 + 执行回填(002 §5)。

    owner_id 为资源属主(会话用户 id),用于端侧工具经浏览器隧道路由;
    为 None 或浏览器未连接时,端侧工具降级为 await_external SSE + 暂停。
    allowed_kb_ids 为知识库检索允许范围(M12,chat 侧组装,设计 008 §3.3)。
    chat_session_id 为所属聊天会话(M25 交付物登记用;不传则不登记)。
    """
    tools = await build_tools(session, resource_ids)
    resources: dict[str, SkillTool] = {}
    for rid in resource_ids:
        row = await resolve(session, rid)
        if row is not None:
            # 部署态自愈:陈旧资源行的 impl 文件缺失时从 manifest 重建(20260929 事故)
            from agentplatform.core.plugin.loader import ensure_resource_impl

            await ensure_resource_impl(session, row)
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
        list(resources.values()), plugin_desc=plugin_desc, memories=memories,
        display_name=display_name,
    )
    messages = build_messages(system, history, user_message, images=images)

    import asyncio
    skill_delta_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def skill_call(prompt: str) -> str:
        """简单 skill 的一次 LLM 调用(002 §5.3)。实时将 delta 注入队列以流式渲染给用户。

        嵌套流失败不再静默(20260928 断流事故):client 以 error 事件上报的失败
        回填为可见错误文本进结果与队列,外层模型据此自纠,而不是拿到空串无声停摆。
        """
        chunks: list[str] = []
        async for e in _stream(llm_client, [{"role": "user", "content": prompt}]):
            if e.type == "delta" and e.text:
                chunks.append(e.text)
                await skill_delta_queue.put(e.text)
            elif e.type == "error" and getattr(e, "error", None):
                err_text = f"\n\n【skill 子调用失败】{e.error}"
                chunks.append(err_text)
                await skill_delta_queue.put(err_text)
        return "".join(chunks)

    async def execute(resource: SkillTool | None, arguments: str) -> str:
        """执行入口:包装 _execute_inner,采集产物 URL 与入参消费(freshness 校验用)。"""
        import re as _re

        # 属性快照:执行期间请求级 session 可能已 rollback/关闭(expire/detach),
        # 执行完成后再摸 ORM 属性会触发刷新抛 DetachedInstanceError(20260928 断流事故)
        rid = resource.id if resource is not None else None
        rkind = resource.kind if resource is not None else None
        rver = resource.version if resource is not None else None
        # 入参引用了平台文件 URL(签名/编码形态)→ 记为已消费(交付链:
        # 如 image_gen 的图被嵌进 preview 的 html_content)
        arg_urls = set(
            _re.findall(r'https?://[^\s\"<>]+|/api/files/raw\?[^\s\"<>]+', arguments or "")
        )
        if arg_urls:
            _run_state.consumed_urls.update(u for u in arg_urls if "%" in u or "sig=" in u)
        result = await _execute_inner(resource, arguments)
        # M26 使用计数(设计 020 §2):tool/skill 每次执行 +1(内部静默自愈)
        if rid and rver:
            from agentplatform.core.registry.service import bump_use_count

            await bump_use_count(session, rid, rver)
        if rid and rkind == SkillToolKind.tool:
            urls = set(
                _re.findall(r'https?://[^\s\"<>]+|/api/files/raw\?[^\s\"<>]+', result or "")
            )
            if urls:
                _run_state.produced_urls.setdefault(rid, set()).update(urls)
            # M25 交付物登记(设计 019 §3.1):白名单工具产物落 artifacts;
            # 登记内部自愈,失败仅日志
            from agentplatform.core.artifacts.service import register_tool_artifact

            await register_tool_artifact(
                session,
                tool_id=rid,
                result=result or "",
                args=_parse_args(arguments),
                owner_id=owner_id,
                chat_session_id=chat_session_id,
            )
        return result

    # M17 P1:写操作确认框积攒区(执行后由 block_meta 通道下发)
    pending_confirm_blocks: list[dict] = []
    # T18.3 编排保障:本轮已执行的 tool/skill id(终答前 required_tools 校验用)
    executed_tool_ids: set[str] = set()
    executed_skill_ids: set[str] = set()
    orchestration_nudged = False

    class _RunState:
        """跨内部函数共享的可变状态。
        produced_urls: tool id → 其结果产出的 URL 集合;
        consumed_urls: 后续工具入参中出现过的平台 URL(交付链消费,
        如 image_gen 产物被嵌进 preview 的 html_content——freshness 判"已使用")。
        """

        produced_urls: dict[str, set[str]] = {}
        consumed_urls: set[str] = set()

    _run_state = _RunState()

    async def _execute_inner(resource: SkillTool | None, arguments: str) -> str:
        """执行单个 tool_call,任何异常都回填为文本(让 LLM 可自纠)。"""
        if resource is None:
            return "错误:未找到该资源"
        args = _parse_args(arguments)
        if resource.id:
            (executed_skill_ids if resource.kind == SkillToolKind.skill else executed_tool_ids).add(resource.id)

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
            if resource.id == IMAGE_GEN_TOOL_ID:
                # 文生图:无 DB 依赖,产物落盘 uploads 经 files 通道回 URL(M18)
                return await image_gen_run(args)
            if resource.id == HTML_RENDER_TOOL_ID:
                # HTML 渲染:sidecar 承载,产物签名 URL(T18.17)
                return await html_render_run(args)
            # Schema 驱动表单(控件零感知):skill 缺 required 参数时,不靠模型文本追问,
            # 平台按 schema 自动生成 input.form 下发;回填值经【表单提交】进会话,
            # 下一轮模型带齐参数再调 skill。仅拦 skill(工具参数由模型从上下文组装)。
            if (
                resource.kind == SkillToolKind.skill
                and resource.id != KB_SEARCH_TOOL_ID
            ):
                from agentplatform.core.agent.schema_form import form_block_for, missing_required

                schema_dict = (getattr(resource, "schema_", None) or {}).get("parameters")
                if missing_required(schema_dict, args):
                    block = form_block_for(resource.name or resource.id, schema_dict)
                    if block is not None:
                        pending_confirm_blocks.append(block)
                        return json.dumps(
                            {
                                "status": "awaiting_form",
                                "message": (
                                    f"技能 {resource.name or resource.id} 缺少必填参数,已向用户下发"
                                    "按参数 schema 自动生成的表单;等待【表单提交】后再调用本技能执行"
                                ),
                            },
                            ensure_ascii=False,
                        )
            if resource.id == HTTP_ACTION_TOOL_ID:
                # 通用 HTTP 动作:白名单+SSRF 约束(M17);写操作挂起等用户确认(M17 P1)
                # user/session 透传供审计留痕(M17 P1)
                result = await http_action_run(args, user_id=owner_id or "", session_id=None)
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

        if not calls and not getattr(llm_client, "supports_native_tools", False):
            # H5 分流:端点确认原生(supports_native_tools=true)才跳过文本兜底;
            # 默认保持兜底——现网模型存在文本语法混用(20261003 回归实证)
            calls = _extract_text_tool_calls(accumulated_text, resources)

        if not calls:
            # T18.3 编排保障:已执行 skill 的 required_tools 终答前校验;两类违规同款有界补调(一次):
            # ① 缺失——必经工具本轮未被调用;② 不新鲜——已调用但产物 URL 未嵌入正文
            #    (复用历史旧图等形态,writewx 20260928-1201 验收发现)
            if not orchestration_nudged:
                required: set[str] = set()
                # 声明来源:已执行的 skill 行 + tool 行(插件级声明并入每个资源行,
                # 覆盖"模型不经 skill 直接产出"形态)
                for rid in executed_skill_ids | executed_tool_ids:
                    row = resources.get(rid)
                    rt = ((getattr(row, "schema_", None) or {}).get("required_tools")) if row else None
                    if isinstance(rt, list):
                        required |= {str(x) for x in rt}
                missing = required - executed_tool_ids
                _log_orchestration(required, executed_tool_ids, executed_skill_ids, missing)
                stale: set[str] = set()
                if not missing and required:
                    # freshness 独立判定(20260928-1348):不再以"正文含 <img>"为前提——
                    # 定向场景正文可以只有"完成"两字,产物未被任何通道消费才是判定依据。
                    # 消费定义:产物 URL 出现在 chat 正文,或被任一后续工具入参引用
                    # (交付链,如 preview 的 html_content)。
                    produced = _run_state.produced_urls
                    consumed = _run_state.consumed_urls
                    stale = required - {
                        tid for tid in required
                        if any(
                            u in accumulated_text or u in consumed
                            for u in produced.get(tid, set())
                        )
                    }
                if missing or stale:
                    orchestration_nudged = True
                    target = sorted(missing or stale)
                    reason = (
                        "你的交付遗漏了必经步骤" if missing
                        else "你的交付未使用必经工具本会话产出的资源(疑似复用旧资源)"
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"【系统校验】{reason}: "
                                + "、".join(target)
                                + "。请立即真实调用上述工具并在交付中引用其本次产物"
                                "(严禁只口头声称或复用旧资源);若确无法调用,如实说明原因。"
                            ),
                        }
                    )
                    yield AgentEvent(
                        type="delta",
                        text="\n\n*(系统:检测到交付校验未过,已要求助手补齐)*\n\n",
                    )
                    continue
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
                        async for ev in _drain_until_done(route_task, progress_q):
                            yield ev

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
                    try:
                        async for chunk in _drain_until_done(exec_task, skill_delta_queue):
                            if chunk:
                                yield AgentEvent(type="skill_delta", text=chunk)

                        result = await exec_task
                    finally:
                        # 客户端断开/生成器被取消时终止孤儿执行任务:否则任务继续持有
                        # 已关闭的请求级 session,产生 DetachedInstanceError 与连接泄漏
                        # (20260928 断流事故日志证据:Task exception was never retrieved)
                        if not exec_task.done():
                            exec_task.cancel()
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





def _stream(
    llm_client: object, messages: list[dict], tools: list[dict] | None = None
) -> AsyncIterator:
    """适配:客户端 stream(messages, tools) 的鸭子接口。"""
    return llm_client.stream(messages, tools)  # type: ignore[attr-defined]




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



