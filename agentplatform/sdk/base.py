"""SDK 基类与上下文(设计 006 §3-5)。

Skill:能力/知识单元,含 prompt 模板与 render(填充 {{var}});
Tool:确定性编程接口(函数或类)。Context 承载运行时上下文(会话/注入)。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def get_plugin_data_dir(plugin_name: str | None = None) -> Path:
    """获取当前插件专属持久化数据目录。

    解析顺序：
    1. 环境变量 AGENTPLATFORM_PLUGIN_DATA_DIR；
    2. 若未注入，则回退到 ~/.agentplatform/plugins/<plugin_name>/data/ (默认 plugin_name 为 'default')；
    3. 自动递归创建该目录并返回 Path 对象。
    """
    env_dir = os.environ.get("AGENTPLATFORM_PLUGIN_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
    else:
        name = plugin_name or "default"
        path = Path.home() / ".agentplatform" / "plugins" / name / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_base_url() -> str:
    """获取平台服务 Base URL。

    解析顺序：
    1. 环境变量 AGENTPLATFORM_BASE_URL；
    2. 环境变量 AGENTPLATFORM_TARGET；
    3. 默认 http://localhost:8000。
    """
    return (
        os.environ.get("AGENTPLATFORM_BASE_URL")
        or os.environ.get("AGENTPLATFORM_TARGET")
        or "http://localhost:8000"
    ).rstrip("/")


@dataclass
class Context:
    """运行时上下文(会话 id、附加信息;dev/平台共用)。"""

    session_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        """插件专属数据持久化目录。"""
        return get_plugin_data_dir()

    @property
    def base_url(self) -> str:
        """平台基础服务地址。"""
        return get_base_url()


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
