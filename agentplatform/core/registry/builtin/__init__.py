"""平台内置 skill/tool 资源(设计 002 §3.2,source=builtin)。

每个模块自描述 RESOURCE 元信息 + 可调用实现(run / build_prompt);
种子脚本与 M5 执行器按同一接口使用。
"""

from agentplatform.core.registry.builtin import pdf_parse, structured_output, summarize
from agentplatform.core.registry.builtin.meta import ResourceMeta

__all__ = ["ALL", "ResourceMeta", "pdf_parse", "structured_output", "summarize"]

# 内置资源清单:元信息 + 实现随模块演进,种子/注册共用
ALL: tuple[ResourceMeta, ...] = (
    pdf_parse.RESOURCE,
    summarize.RESOURCE,
    structured_output.RESOURCE,
)
