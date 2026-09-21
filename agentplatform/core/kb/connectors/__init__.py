"""内容型连接器包(设计 009):导入即自注册各 adapter。"""

from agentplatform.core.kb.connectors import web as _web  # noqa: F401  导入即注册 web adapter
from agentplatform.core.kb.connectors import github as _github  # noqa: F401  M13 P1:GitHub adapter
from agentplatform.core.kb.connectors import gitlab as _gitlab  # noqa: F401  离职归档:自托管 GitLab adapter
