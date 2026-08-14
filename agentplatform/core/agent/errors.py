"""agent 运行时错误。"""


class AgentError(Exception):
    """agent 运行时错误基类。"""


class AgentExecError(AgentError):
    """资源实现解析/执行失败。"""


class AgentLoopError(AgentError):
    """调度循环失败(如 LLM 调用错误)。"""
