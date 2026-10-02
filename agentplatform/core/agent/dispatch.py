"""工具调用解析与资源匹配(设计 016 §3 / M21 P2.4,自 loop.py 迁出)。

文本兜底解析(截断启发式)对模型输出格式敏感——集中于此便于 H5 按端点
能力分流与可观测收敛。
"""

import json
import re

from agentplatform.core.agent.errors import AgentExecError  # noqa: F401
from agentplatform.core.registry.model import SkillTool

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

def _parse_args(arguments: str) -> dict:
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}

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

def _extract_text_tool_calls(text: str, resources: dict[str, SkillTool]) -> list:
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

    from agentplatform.core.llm.client import ToolCall

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

        # 7. 自然语言草稿箱注入意图兜底: 模型口头承诺"调用草稿箱注入"且当前消息携带
        #    真实文章 HTML 时,代为发起注入并按契约补全 title/html_content 参数。
        #    安全边界(2026-09-26 修复):仅在确有文章载荷时触发——问候语里的能力介绍
        #    ("自动注入草稿箱")、成功话术("注入完成")一律不得变成幽灵工具调用;
        #    空载荷注入违反工具契约(title/html_content 必填),曾导致空文章注入风险。
        nl_draft = re.search(
            r"(?:调用|使用|重新调用|执行|发起)\s*[`']?(?:tool:)?(?:browser_wechat_draft|草稿箱注入)[`']?|(?:将文章|正在将文章|开始)注入.*微信.*草稿箱",
            text,
        )
        if nl_draft and any("browser_wechat_draft" in rid for rid in resources):
            draft_html = _extract_html_fallback(text)
            if draft_html:
                draft_title_m = (
                    re.search(r"<title>([^<]+)</title>", draft_html, re.IGNORECASE)
                    or re.search(r"<h1[^>]*>([^<]+)</h1>", draft_html, re.IGNORECASE)
                )
                draft_args = {
                    "title": draft_title_m.group(1).strip() if draft_title_m else "未命名文章",
                    "html_content": draft_html,
                }
                target_res = next((rid for rid in resources if "browser_wechat_draft" in rid), "tool:browser_wechat_draft")
                extracted.append(
                    ToolCall(
                        id=f"call_draft_{uuid.uuid4().hex[:8]}",
                        name=target_res.replace(":", "__"),
                        arguments=json.dumps(draft_args, ensure_ascii=False),
                    )
                )

    return extracted
