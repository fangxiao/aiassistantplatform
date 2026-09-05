"""tool:browser_list_tabs —— 获取当前浏览器打开的标签页列表 (端侧真机工具)。

通过端侧 WebSocket 隧道 (BrowserBridge) 路由至用户本地 Chrome 扩展 (BrowserAgent)，
获取当前所有打开标签页的 tabId、URL 与标题。
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "tool:browser_list_tabs",
    "kind": "tool",
    "name": "browser_list_tabs",
    "version": "1.0.0",
    "description": "通过用户本地 Chrome 扩展，获取当前浏览器中所有打开标签页的列表 (tabId, url, title)",
    "impl_path": "endpoint:browser.list_tabs",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "returns": {
            "type": "array",
            "items": {"type": "object"},
            "description": "标签页列表",
        },
    },
}
