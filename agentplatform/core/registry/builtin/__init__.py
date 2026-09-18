"""平台内置 skill/tool 资源(设计 002 §3.2,source=builtin)。

每个模块自描述 RESOURCE 元信息 + 可调用实现(run / build_prompt);
种子脚本与 M5 执行器按同一接口使用。

注:tool:workbench_todo 的实现位于 core/workbench/todo_tool.py(与待办服务同域),
此处仅登记其 RESOURCE 进 ALL——它经由 workbench 包导入。
"""

from agentplatform.core.registry.builtin import (
    browser_action,
    browser_extract_dom,
    browser_list_tabs,
    browser_wechat_draft,
    cross_document_compare,
    html_cleaner,
    kb_search,
    pdf_parse,
    structured_output,
    summarize,
)
from agentplatform.core.registry.builtin.meta import ResourceMeta
from agentplatform.core.agent.web_search import RESOURCE as _web_search_resource
from agentplatform.core.memory.tool import RESOURCE as _memory_resource
from agentplatform.core.workbench.todo_tool import RESOURCE as _workbench_todo_resource

__all__ = [
    "ALL",
    "ResourceMeta",
    "browser_action",
    "browser_extract_dom",
    "browser_list_tabs",
    "browser_wechat_draft",
    "cross_document_compare",
    "html_cleaner",
    "kb_search",
    "pdf_parse",
    "structured_output",
    "summarize",
]

# 内置资源清单:元信息 + 实现随模块演进,种子/注册共用
ALL: tuple[ResourceMeta, ...] = (
    cross_document_compare.RESOURCE,
    html_cleaner.RESOURCE,
    pdf_parse.RESOURCE,
    summarize.RESOURCE,
    structured_output.RESOURCE,
    browser_wechat_draft.RESOURCE,
    browser_extract_dom.RESOURCE,
    browser_action.RESOURCE,
    browser_list_tabs.RESOURCE,
    kb_search.RESOURCE,
    _workbench_todo_resource,
    _web_search_resource,
    _memory_resource,
)
