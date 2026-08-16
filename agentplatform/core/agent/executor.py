"""tool/skill 执行器(设计 002 §5.3 / 001 §core/agent)。

tool:确定性接口,按 impl_path 导入模块调用 run(**args)。
skill:简单 skill,填充 prompt 模板后由注入的 llm_call 完成一次 LLM 调用。
插件代码未上传时(impl_path 指向插件内文件)抛 AgentExecError;
代码上传与加载在 M9 引入,走同一路径。
"""

import importlib
import importlib.util
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from agentplatform.core.agent.errors import AgentExecError
from agentplatform.core.registry.model import SkillTool

# skill 的 LLM 调用器:prompt -> 文本(测试可 mock,生产由循环注入)
SkillLlmCall = Callable[[str], Awaitable[str]]


# 内存实现注册表 (供本地 dev / 测试时直接绑定插件中的 callable，无需磁盘打包路径)
_DEV_REGISTRY: dict[str, Callable] = {}


def register_dev_impl(resource_id: str, impl_callable: Callable) -> None:
    """在当前进程注册本地内存实现 (dev / 测试使用)。"""
    _DEV_REGISTRY[resource_id] = impl_callable


def clear_dev_registry() -> None:
    """清理内存注册表。"""
    _DEV_REGISTRY.clear()


def resolve_impl(resource: SkillTool) -> object:
    """按 impl_path 解析实现模块;builtin 直接导入;插件代码按文件路径动态加载。"""
    path = resource.impl_path
    if not path:
        raise AgentExecError(f"资源 {resource.id} 缺少 impl_path")

    p = Path(path)
    if p.exists() and (path.endswith(".py") or p.is_file()):
        # 注入插件工程根目录及 .venv site-packages 到 sys.path
        parent_dir = str(p.parent.parent.resolve())
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        for parent in p.parents:
            for venv_site in parent.glob(".venv/lib/python*/site-packages"):
                sp_str = str(venv_site.resolve())
                if sp_str not in sys.path:
                    sys.path.insert(0, sp_str)

        module_name = f"agentplatform_plugin_module_{abs(hash(str(p.resolve())))}"
        if module_name in sys.modules:
            return sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, str(p.resolve()))
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module
        raise AgentExecError(f"无法加载插件模块: {path}")



    # 相对文件路径且文件不存在
    if path.startswith((".", "/")) or path.endswith(".py"):
        raise AgentExecError(
            f"资源 {resource.id} 的实现文件不存在: {path}(插件代码上传在 M9 支持)"
        )
    try:
        return importlib.import_module(path)
    except (ModuleNotFoundError, TypeError, ValueError) as exc:
        raise AgentExecError(f"资源 {resource.id} 的实现无法加载: {path}") from exc


async def execute_tool(resource: SkillTool, args: dict) -> str:
    """执行确定性 tool,返回可回填的字符串结果。"""
    if resource.id in _DEV_REGISTRY:
        impl = _DEV_REGISTRY[resource.id]
        result = impl(args)
        if hasattr(result, "__await__"):
            result = await result
        return result if isinstance(result, str) else str(result)

    impl = resolve_impl(resource)
    run_fn = getattr(impl, "run", None)
    if run_fn is None and hasattr(impl, "__tool_registry__"):
        for entry in getattr(impl, "__tool_registry__", []):
            if entry["id"] == resource.id:
                from agentplatform.sdk.decorators import as_tool_callable
                run_fn = as_tool_callable(entry["obj"])
                break
    if run_fn is None:
        raise AgentExecError(f"资源 {resource.id} 缺少 run 实现")

    try:
        result = run_fn(**args)
    except TypeError:
        result = run_fn(args) if callable(run_fn) else str(run_fn)


    if hasattr(result, "__await__"):
        result = await result
    return result if isinstance(result, str) else str(result)


async def execute_skill(resource: SkillTool, args: dict, llm_call: SkillLlmCall) -> str:
    """执行简单 skill: 填充 prompt 模板 + 一次 LLM 调用 (002 §5.3)。支持无本地文件时的元数据优雅降级。"""
    if resource.id in _DEV_REGISTRY:
        impl = _DEV_REGISTRY[resource.id]
        prompt = impl(args)
        if hasattr(prompt, "__await__"):
            prompt = await prompt
        return await llm_call(str(prompt))

    try:
        impl = resolve_impl(resource)
    except AgentExecError:
        # 优雅降级：如果无本地实现文件（如纯 Prompt 声明或跨机器部署），通过资源描述与参数动态构建提示词
        import json

        args_str = json.dumps(args, ensure_ascii=False, indent=2)
        desc = resource.description or resource.name
        prompt = (
            f"请作为专业技能 [{resource.name}] 执行以下任务。\n"
            f"技能说明: {desc}\n"
            f"输入参数:\n{args_str}\n\n"
            f"请根据上述要求与参数完成处理并输出专业、详尽的结果。"
        )
        return await llm_call(prompt)

    if hasattr(impl, "__skill_registry__"):
        for entry in getattr(impl, "__skill_registry__", []):
            if entry["id"] == resource.id:
                from agentplatform.sdk.decorators import as_skill_callable

                callable_skill = as_skill_callable(entry["cls"])
                prompt = callable_skill(args)
                if hasattr(prompt, "__await__"):
                    prompt = await prompt
                return await llm_call(str(prompt))

    build = getattr(impl, "build_prompt", None)
    if build is None:
        import json

        args_str = json.dumps(args, ensure_ascii=False, indent=2)
        desc = resource.description or resource.name
        prompt = f"请作为技能 [{resource.name}] ({desc}) 处理以下参数:\n{args_str}"
        return await llm_call(prompt)
    prompt = build(**args)
    return await llm_call(prompt)



