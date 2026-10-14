"""M38 拦截器管道测试(RFC-01):四钩子执行顺序/脱敏/终止/透传。"""

import pytest

from agentplatform.core.agent.interceptors import (
    BaseInterceptor,
    DataMaskingInterceptor,
    InterceptorAbort,
    InterceptorContext,
    clear_interceptors,
    register_interceptor,
    run_after_llm,
    run_after_tool,
    run_before_llm,
    run_before_tool,
)


@pytest.fixture(autouse=True)
def _clean():
    clear_interceptors()
    yield
    clear_interceptors()


def test_passthrough_no_interceptors():
    """无拦截器时消息原样透传。"""
    import asyncio

    ctx = InterceptorContext(session_id="s", user_id="u")
    msgs = [{"role": "user", "content": "hello"}]
    result = asyncio.run(run_before_llm(msgs, ctx))
    assert result == msgs
    text = asyncio.run(run_after_llm("reply", ctx))
    assert text == "reply"


def test_data_masking_masks_ids():
    """身份证/手机号/银行卡脱敏。"""
    import asyncio

    register_interceptor(DataMaskingInterceptor())
    ctx = InterceptorContext()
    msgs = [{"role": "user", "content": "我的身份证是110101199001011234手机13912345678"}]
    result = asyncio.run(run_before_llm(msgs, ctx))
    assert "110****1234" in result[0]["content"]
    assert "139****5678" in result[0]["content"]
    assert "110101199001011234" not in result[0]["content"]


def test_interceptor_abort():
    """拦截器抛 Abort → 异常上抛(调度层转为用户可见消息)。"""
    import asyncio

    class Blocker(BaseInterceptor):
        name = "blocker"

        async def before_tool_execution(self, tool_name, tool_args, ctx):
            if tool_name == "dangerous_tool":
                raise InterceptorAbort("该操作已被安全策略禁止")
            return tool_args

    register_interceptor(Blocker())
    ctx = InterceptorContext()
    with pytest.raises(InterceptorAbort, match="安全策略"):
        asyncio.run(run_before_tool("dangerous_tool", {"x": 1}, ctx))
    # 安全工具不受影响
    result = asyncio.run(run_before_tool("safe_tool", {"x": 1}, ctx))
    assert result == {"x": 1}


def test_chain_order():
    """多拦截器按注册顺序执行。"""
    import asyncio

    order = []

    class First(BaseInterceptor):
        name = "first"

        async def after_llm_response(self, text, ctx):
            order.append("first")
            return text + "→1"

    class Second(BaseInterceptor):
        name = "second"

        async def after_llm_response(self, text, ctx):
            order.append("second")
            return text + "→2"

    register_interceptor(First())
    register_interceptor(Second())
    result = asyncio.run(run_after_llm("start", InterceptorContext()))
    assert result == "start→1→2"
    assert order == ["first", "second"]


def test_tool_hooks_modify_args_and_result():
    """before_tool 修改参数;after_tool 修改结果。"""
    import asyncio

    class Modifier(BaseInterceptor):
        name = "modifier"

        async def before_tool_execution(self, tool_name, tool_args, ctx):
            tool_args["injected"] = True
            return tool_args

        async def after_tool_execution(self, tool_name, tool_result, ctx):
            return f"[masked] {tool_result}"

    register_interceptor(Modifier())
    ctx = InterceptorContext()
    args = asyncio.run(run_before_tool("my_tool", {"a": 1}, ctx))
    assert args == {"a": 1, "injected": True}
    result = asyncio.run(run_after_tool("my_tool", "raw output", ctx))
    assert result == "[masked] raw output"
