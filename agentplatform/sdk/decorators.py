"""SDK 装饰器(设计 006 §3-4):@skill / @tool 注册元信息并收集到模块注册表。

装饰后的类/函数在模块级 `__skill_registry__` / `__tool_registry__` 登记,
供 loader.resources_from_module 提取(CLI validate / deploy 使用)。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any, TypeVar, cast

from agentplatform.sdk.base import Context, Skill, Tool

T = TypeVar("T")


def _collect(module: Any, name: str, entry: dict) -> None:
    reg = getattr(module, name, None)
    if not isinstance(reg, list):
        reg = []
        setattr(module, name, reg)
    reg.append(entry)


def _caller_module(obj: Any) -> Any:
    return sys.modules.get(getattr(obj, "__module__", ""), sys.modules["__main__"])


def skill(
    id: str,
    version: str,
    description: str | None = None,
    schema: dict | None = None,
    prompt: str | None = None,
) -> Callable[[type[Skill]], type[Skill]]:
    """类装饰器:注册 skill 元信息(006 §3)。"""

    def decorate(cls: type[Skill]) -> type[Skill]:
        cls.description = str(description or getattr(cls, "description", ""))
        cls.schema = schema or getattr(cls, "schema", {"type": "object", "properties": {}})
        cls.prompt = str(prompt or getattr(cls, "prompt", ""))
        _collect(
            _caller_module(cls),
            "__skill_registry__",
            {"cls": cls, "id": id, "version": version},
        )
        return cls

    return decorate


def tool(
    id: str,
    version: str,
    description: str | None = None,
    schema: dict | None = None,
) -> Callable[[T], T]:
    """函数/类装饰器:注册 tool 元信息(006 §4)。"""

    def decorate(obj: T) -> T:
        _collect(
            _caller_module(obj),
            "__tool_registry__",
            {"obj": obj, "id": id, "version": version},
        )
        _any = cast(Any, obj)
        if description:
            _any.description = description
        if schema:
            _any.schema = schema
        return obj

    return decorate


def as_tool_callable(obj: Any) -> Callable[..., Any]:
    """把 @tool 装饰的对象统一为可调用;返回值交由执行器归一化(await/str)。

    此处不得提前 str() 包装:async 工具返回 coroutine,提前 str() 会把它变成
    "<coroutine object ...>",执行器的 __await__ 检查永远命不中,真实逻辑不执行
    (20261016 savetoken 工单 20261016-2303-3e006b 实证)。
    """
    if isinstance(obj, type) and issubclass(obj, Tool):
        return lambda args: obj().run(args)
    if isinstance(obj, type):
        return lambda args: obj().run(args)
    if callable(obj):
        return lambda args: obj(**args) if args else obj()
    raise TypeError(f"无法作为 tool 调用: {obj!r}")


def as_skill_callable(cls: type[Skill]) -> Callable[[dict], str]:
    """把 @skill 装饰的类统一为 execute(ctx, args)->str 调用(简单形态)。"""
    return lambda args: cls().execute(Context(), args)
