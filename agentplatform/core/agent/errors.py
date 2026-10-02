"""agent 运行时错误 + 错误分类体系(需求 011 H4 / ADR 0010)。

六类错误绑定处理策略:
- transient          网络/超时/限流 → 通道层自动重试(LLM client 已有端点级重试)
- checkpoint_resume  流中断可续跑 → 检查点保留 + resume 端点
- tool_failure       工具执行失败 → 结果回填模型自纠
- deploy_broken      部署态断线(impl 缺失等) → 自愈(ensure_resource_impl)→ 明确报错
- contract           模型输出不合契约(工具调用解析失败等) → 有界重试
- internal           平台内部错误 → 落日志 + 结构化错误事件
"""


import asyncio
from enum import Enum


class AgentError(Exception):
    """agent 运行时错误基类。"""


class AgentExecError(AgentError):
    """资源实现解析/执行失败。"""


class AgentLoopError(AgentError):
    """调度循环失败(如 LLM 调用错误)。"""


class ErrorKind(str, Enum):
    """错误六分类(ADR 0010)。新增错误类型先归入既有类并补策略声明。"""

    transient = "transient"
    checkpoint_resume = "checkpoint_resume"
    tool_failure = "tool_failure"
    deploy_broken = "deploy_broken"
    contract = "contract"
    internal = "internal"


# classify_exception 依据的特征串(部署态断线:executor/自愈路径的报错文案)
_DEPLOY_BROKEN_MARKERS = ("实现文件不存在", "impl 文件缺失", "无法加载插件模块", "缺少 impl_path")


def classify_exception(exc: BaseException) -> tuple[ErrorKind, bool]:
    """异常 → (错误类别, 是否可续跑)。SSE error 事件与 trace 共用的唯一定义点。"""
    msg = str(exc)
    if isinstance(exc, AgentExecError):
        if any(m in msg for m in _DEPLOY_BROKEN_MARKERS):
            return ErrorKind.deploy_broken, False
        return ErrorKind.tool_failure, False
    if isinstance(exc, AgentLoopError):
        return ErrorKind.transient, True
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return ErrorKind.transient, True
    if any(k in type(exc).__name__.lower() for k in ("timeout", "connect")) or (
        "timed out" in msg or "connection" in msg.lower()
    ):
        return ErrorKind.transient, True
    return ErrorKind.internal, True  # 未知异常:检查点已留,resumable 兜底为真
