"""tool/skill 执行器(设计 002 §5.3 / 001 §core/agent)。

tool:确定性接口,按 impl_path 导入模块调用 run(**args)。
skill:简单 skill,填充 prompt 模板后由注入的 llm_call 完成一次 LLM 调用。
插件代码未上传时(impl_path 指向插件内文件)抛 AgentExecError;
代码上传与加载在 M9 引入,走同一路径。
"""

import importlib
from collections.abc import Awaitable, Callable

from agentplatform.core.agent.errors import AgentExecError
from agentplatform.core.registry.model import SkillTool

# skill 的 LLM 调用器:prompt -> 文本(测试可 mock,生产由循环注入)
SkillLlmCall = Callable[[str], Awaitable[str]]


def resolve_impl(resource: SkillTool) -> object:
    """按 impl_path 解析实现模块;builtin 直接导入,插件代码未加载时明确报错。"""
    path = resource.impl_path
    if not path:
        raise AgentExecError(f"资源 {resource.id} 缺少 impl_path")
    # 相对文件路径 = 插件内代码(尚未上传加载,M9 引入代码上传)
    if path.startswith((".", "/")) or path.endswith(".py"):
        raise AgentExecError(
            f"资源 {resource.id} 的实现未加载: {path}(插件代码上传在 M9 支持)"
        )
    try:
        return importlib.import_module(path)
    except (ModuleNotFoundError, TypeError, ValueError) as exc:
        raise AgentExecError(f"资源 {resource.id} 的实现无法加载: {path}") from exc


async def execute_tool(resource: SkillTool, args: dict) -> str:
    """执行确定性 tool,返回可回填的字符串结果。"""
    impl = resolve_impl(resource)
    run = getattr(impl, "run", None)
    if run is None:
        raise AgentExecError(f"资源 {resource.id} 缺少 run 实现")
    result = run(**args)
    return result if isinstance(result, str) else str(result)


async def execute_skill(resource: SkillTool, args: dict, llm_call: SkillLlmCall) -> str:
    """执行简单 skill:填充 prompt 模板 + 一次 LLM 调用(002 §5.3)。"""
    impl = resolve_impl(resource)
    build = getattr(impl, "build_prompt", None)
    if build is None:
        raise AgentExecError(f"skill {resource.id} 缺少 build_prompt 实现")
    prompt = build(**args)
    return await llm_call(prompt)
