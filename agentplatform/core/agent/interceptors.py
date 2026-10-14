"""管道拦截器(M38/RFC-01):LLM 调用与工具执行的全局钩子管道。

机制与策略分离:平台只提供钩子点与执行顺序,脱敏/审计/审查由拦截器实现。
拦截器按注册顺序执行;抛出 InterceptorAbort 安全终止会话。
"""

import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class InterceptorAbort(Exception):
    """拦截器要求终止会话(如检测到严重违规);message 会推送给用户。"""

    def __init__(self, message: str, code: str = "interceptor_abort"):
        self.message = message
        self.code = code
        super().__init__(message)


@dataclass
class InterceptorContext:
    """拦截器执行上下文(会话级信息,只读)。"""

    session_id: str = ""
    user_id: str = ""
    plugin_name: str = ""
    # 扩展槽(企业可注入租户/环境等)
    extra: dict[str, Any] = field(default_factory=dict)


class BaseInterceptor(ABC):
    """平台消息与工具执行拦截器基类(RFC-01 §1.2)。

    四个钩子全部可选(默认透传);子类按需覆写。
    """

    name: str = "base"

    async def before_llm_request(
        self, messages: list[dict], ctx: InterceptorContext
    ) -> list[dict]:
        """LLM 调用前:可脱敏/注入 system prompt/修改消息。返回修改后的 messages。"""
        return messages

    async def after_llm_response(
        self, response_text: str, ctx: InterceptorContext
    ) -> str:
        """LLM 输出后:可脱敏/审查/格式化。返回处理后的文本。"""
        return response_text

    async def before_tool_execution(
        self, tool_name: str, tool_args: dict[str, Any], ctx: InterceptorContext
    ) -> dict[str, Any]:
        """工具执行前:可校验参数/修改参数/拒绝执行(抛 InterceptorAbort)。"""
        return tool_args

    async def after_tool_execution(
        self, tool_name: str, tool_result: Any, ctx: InterceptorContext
    ) -> Any:
        """工具执行后:可对结果脱敏/格式化。返回处理后的结果。"""
        return tool_result


# ── 内置:脱敏拦截器示例(身份证/手机号/银行卡)────────────────

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # (?<!\d)/(?!\d) 代替 \b:中文字符是 word char,\b 在中文旁不生效
    ("身份证", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("银行卡", re.compile(r"(?<!\d)\d{16,19}(?!\d)")),
]


def _mask(text: str) -> str:
    for label, pat in _PATTERNS:
        text = pat.sub(lambda m: m.group()[:3] + "****" + m.group()[-4:], text)
    return text


class DataMaskingInterceptor(BaseInterceptor):
    """内置示例:身份证/手机号/银行卡自动脱敏(RFC-01 验收样例)。

    before_llm_request:对消息中的敏感号码打码(防止发给 LLM)。
    after_llm_response:对 LLM 输出中的号码打码(防止回显)。
    """

    name = "data_masking"

    async def before_llm_request(self, messages, ctx):
        return [{**m, "content": _mask(m.get("content", ""))} if isinstance(m.get("content"), str) else m for m in messages]

    async def after_llm_response(self, response_text, ctx):
        return _mask(response_text)


# ── 管道管理 ──────────────────────────────────────────────────

_pipeline: list[BaseInterceptor] = []


def register_interceptor(interceptor: BaseInterceptor, position: int | None = None) -> None:
    """注册拦截器(默认追加到链尾;position 可插入指定位置)。"""
    if position is not None:
        _pipeline.insert(position, interceptor)
    else:
        _pipeline.append(interceptor)
    logger.info("拦截器已注册: %s (链长 %d)", interceptor.name, len(_pipeline))


def clear_interceptors() -> None:
    """清空拦截器链(测试用)。"""
    _pipeline.clear()


def get_pipeline() -> list[BaseInterceptor]:
    return list(_pipeline)


async def run_before_llm(messages: list[dict], ctx: InterceptorContext) -> list[dict]:
    """按序执行全部 before_llm_request。"""
    for itc in _pipeline:
        messages = await itc.before_llm_request(messages, ctx)
    return messages


async def run_after_llm(text: str, ctx: InterceptorContext) -> str:
    for itc in _pipeline:
        text = await itc.after_llm_response(text, ctx)
    return text


async def run_before_tool(tool_name: str, args: dict, ctx: InterceptorContext) -> dict:
    for itc in _pipeline:
        args = await itc.before_tool_execution(tool_name, args, ctx)
    return args


async def run_after_tool(tool_name: str, result: Any, ctx: InterceptorContext) -> Any:
    for itc in _pipeline:
        result = await itc.after_tool_execution(tool_name, result, ctx)
    return result
