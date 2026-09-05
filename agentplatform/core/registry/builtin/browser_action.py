"""tool:browser_action —— 在当前网页执行拟人化操作 (端侧真机工具)。

通过端侧 WebSocket 隧道 (BrowserBridge) 路由至用户本地 Chrome 扩展 (BrowserAgent)，
在当前激活的标签页中执行点击按钮、代填表单输入框、滚动页面等动作。
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "tool:browser_action",
    "kind": "tool",
    "name": "browser_action",
    "version": "1.0.0",
    "description": "通过用户本地 Chrome 扩展，在当前激活网页执行拟人化操作（点击元素、代填表单、滚动等）",
    "impl_path": "endpoint:browser.action",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click", "fill", "scroll", "hover"],
                    "description": "操作类型: click(点击)|fill(填表)|scroll(滚动)|hover(悬停)",
                },
                "selector": {"type": "string", "description": "目标元素的 CSS 选择器或文本特征"},
                "text": {"type": "string", "description": "当 action=fill 时要填入的文本内容"},
            },
            "required": ["action", "selector"],
        },
        "returns": {"type": "object", "description": "操作执行结果状态"},
    },
}
