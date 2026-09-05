"""tool:kb_search —— 知识库检索(平台内置,M12)。

实现与权限收口在 core/kb/search_tool.py(需会话上下文,不走通用 run() 路径);
本模块只转发注册表自描述元信息。执行由 agent loop 特判分派。
"""

from agentplatform.core.kb.search_tool import RESOURCE

__all__ = ["RESOURCE"]
