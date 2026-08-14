"""SDK 基类与上下文(设计 006 §3-5)。

Skill:能力/知识单元,含 prompt 模板与 render(填充 {{var}});
Tool:确定性编程接口(函数或类)。Context 承载运行时上下文(会话/注入)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Context:
    """运行时上下文(会话 id、附加信息;dev/平台共用)。"""

    session_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_TEMPLATE_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class Skill:
    """skill 基类:描述 + schema + prompt 模板 + 执行入口。"""

    description: str = ""
    schema: dict = {"type": "object", "properties": {}}  # noqa: RUF012
    prompt: str = ""

    def __init__(self, ctx: Context | None = None) -> None:
        self.ctx = ctx or Context()

    def render(self, args: dict[str, Any]) -> str:
        """填充 prompt 模板:{{var}} -> args[var](缺失留空)。"""
        def _fill(m: re.Match[str]) -> str:
            return str(args.get(m.group(1), ""))
        return _TEMPLATE_RE.sub(_fill, self.prompt)

    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        """简单 skill:渲染 prompt 交由 agent 执行(006 §3);子类可覆写。"""
        return self.render(args)


class Tool:
    """tool 基类:确定性接口,子类实现 run(args)。"""

    description: str = ""
    schema: dict = {"type": "object", "properties": {}}  # noqa: RUF012

    def run(self, args: dict[str, Any]) -> str:
        raise NotImplementedError
