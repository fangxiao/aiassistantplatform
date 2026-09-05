"""tool:browser_wechat_draft —— 微信公众号图文草稿一键注入 (端侧真机工具)。

【端侧真机工具架构与契约规范】
1. 架构定位：
   - 类型：端侧真机自动化工具 (Client-Side Bridge Tool)。
   - 零凭据设计 (Zero-Credential Design)：插件侧与服务端完全无需配置任何公众号 AppID、AppSecret、Cookie、账号密码，亦无需维护 WebSocket 隧道状态。
2. 运行机制：
   - 调用经 WebSocket 隧道 (/api/browser/tunnel) 路由至用户本地 Chrome 扩展 (BrowserAgent)；
   - 扩展直接驱动用户本地已登录微信公众平台 (mp.weixin.qq.com) 标签页，将图文、作者、摘要与排版样式一键注入草稿箱编辑器。
3. 前置依赖：
   - 用户本地 Chrome 浏览器运行 BrowserAgent 扩展并与平台建立隧道；
   - 用户在 Chrome 中已登录微信公众平台。
4. 调用参数契约：
   - title (str, 必填): 文章主标题 (建议 64 字以内)
   - html_content (str, 必填): 100% 全内联样式微信排版 HTML 正文
   - author (str, 可选): 文章作者名
   - digest (str, 可选): 图文引言摘要 (建议 120 字以内)
   - theme (str, 可选): 排版主题 (tech-blue|wechat-green|minimal-black)
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "tool:browser_wechat_draft",
    "kind": "tool",
    "name": "browser_wechat_draft",
    "version": "1.0.0",
    "description": "【端侧真机工具·零凭据】通过用户本地 Chrome 扩展将图文一键注入当前已登录的微信公众平台 (mp.weixin.qq.com) 草稿箱；插件侧无需配置账号凭据",
    "impl_path": "endpoint:browser.wechat_draft",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "文章主标题 (建议 64 字以内)"},
                "author": {"type": "string", "description": "文章作者名 (可选)"},
                "digest": {"type": "string", "description": "图文引言摘要 (建议 120 字以内，可选)"},
                "html_content": {"type": "string", "description": "100% 全内联样式微信兼容 HTML 正文"},
                "theme": {
                    "type": "string",
                    "description": "排版主题: tech-blue(科技蓝)|wechat-green(微信绿)|minimal-black(极简黑) (可选)",
                },
            },
            "required": ["title", "html_content"],
        },
        "returns": {"type": "object", "description": "端侧注入执行结果状态 (含 status, tabId, message 等)"},
    },
}

