"""tool:browser_extract_dom —— 提取当前网页 DOM / 正文内容 (端侧真机工具)。

通过端侧 WebSocket 隧道 (BrowserBridge) 路由至用户本地 Chrome 扩展 (BrowserAgent)，
从当前激活的标签页中提取核心正文文本、指定 CSS 选择器节点或表单内容。
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "tool:browser_extract_dom",
    "kind": "tool",
    "name": "browser_extract_dom",
    "version": "1.0.0",
    "description": "通过用户本地 Chrome 扩展，从当前激活网页提取核心正文文本或指定 CSS 选择器的 DOM 结构",
    "impl_path": "endpoint:browser.extract_dom",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "可选的目标 CSS 选择器(缺省提取页面核心正文)",
                },
                "include_html": {
                    "type": "boolean",
                    "description": "是否包含原始 HTML(缺省仅提取纯文本)",
                },
            },
        },
        "returns": {"type": "object", "description": "提取出的网页文本与结构数据"},
    },
}
