"""内容型连接器协议与注册表(设计 009 §3,需求 006)。

adapter 为纯函数模块:不做 DB 操作,凭网络凭据产出内存 FetchResult,
由 connectors/service.py 编排入库。网络经可注入 transport(httpx.MockTransport 测试用)。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FetchedDoc:
    """adapter 产出的标准化外部文档。"""

    external_id: str  # 幂等键:web 为规范化 URL;其余为外部系统稳定 id
    url: str  # 原文链接(溯源,检索结果可点开)
    title: str
    content_markdown: str
    mime: str = "text/markdown"


@dataclass(frozen=True)
class FetchResult:
    """一次抓取的结果。

    full=True 表示本次枚举了该数据源的全部文档(全量型:web/confluence/github),
    orchestrator 可据此检测外部删除;full=False 为增量型(如飞书按更新时间),
    只增改不判删。
    """

    docs: list[FetchedDoc] = field(default_factory=list)
    full: bool = False


# adapter 签名:config/credentials 来自 kb_data_sources 行(密文已解密)
FetchFn = Callable[..., Awaitable[FetchResult]]

ADAPTERS: dict[str, FetchFn] = {}


def register_adapter(source_type: str, fn: FetchFn) -> None:
    """登记 adapter(模块导入时自注册;未登记的 type 建源时拒绝)。"""
    ADAPTERS[source_type] = fn
