"""上下文组装(设计 001 §core/agent / 002 §5 显式调用)。

系统提示告知可显式调用的 skill/tool;消息序列为 [system, ...history, user]。
Redis 会话缓存留 M6(sessions/messages)。
"""

from agentplatform.core.registry.model import SkillTool, SkillToolKind


def build_system_prompt(
    resources: list[SkillTool], plugin_desc: str | None = None
) -> str:
    """系统提示: 说明助手职责、领域规范及可用工具。"""
    lines: list[str] = []
    if plugin_desc:
        lines.append(f"【你的角色与核心定位】\n{plugin_desc}\n")
    else:
        lines.append("【你的角色与核心定位】\n你是由 AgentPlatform 驱动的智能助手，能够协助用户解决各种问题并高效完成任务。\n")

    # 提取技能 Prompt 与领域规范，直接赋予助手专家能力
    skills = [r for r in resources if r.kind == SkillToolKind.skill]
    for s in skills:
        lines.append(f"【专业技能与知识规范 · {s.name or s.id}】\n{s.description or ''}\n")

    # 针对微信写作助手的专业排版与端云闭环铁律
    has_wx = any("writewx" in r.id or "wechat" in r.id for r in resources)
    if has_wx:
        lines.append(
            "【微信公众号专业排版与撰写铁律】\n"
            "1. 100% 纯行内样式 (100% Inline Styles)：微信后台会剔除所有 <style> 标签与外部 class，正文必须直接使用带有 style 样式的 HTML 标签（如 <section style='max-width:677px;margin:0 auto;line-height:2.0;color:#3f3f3f;padding:15px;background:#fff;'>包裹全文）。\n"
            "2. 移动端阅读美学：字号 15.5px~16px，行高 2.0，首行缩进 2em；章节标题使用彩色序号块（<span style='background:#00897B;color:#fff;padding:4px 10px;border-radius:4px;font-weight:bold;margin-right:8px;'>01</span>）；重点金句使用左侧翡翠绿边条高亮卡片（border-left: 4px solid #00897B; background: #f0fdfa; padding: 15px; margin: 20px 0; border-radius: 4px;）。\n"
            "3. 一气呵成直接出文：当用户要求撰写文章时，必须立即流式输出排版精美、结构完整的高质量图文 HTML，严禁只回复'请稍候'、'正在撰写'等空头开场白。\n"
            "4. 自动落盘预览与人机协同：文章正文输出完毕后，调用 `tool:writewx_preview` 工具将 HTML 字符串保存并获取预览文件；向用户展示文件卡片并询问：“文章已完成排版并生成预览文件，是否确认通过 BrowserAgent 注入微信公众号草稿箱？”\n"
            "5. 草稿箱注入：当用户回复确认、注入或重试时，必须立即发起 `tool__browser_wechat_draft` 工具调用（参数：title、digest、html_content），严禁仅输出文字空口声称已注入成功或假装调用！"
        )
    else:
        lines.append(
            "【通用执行准则】\n"
            "1. 直接行动：针对用户的提问或任务，直接给出清晰、准确、详实且专业的回复或执行结果，严禁只口头承诺而不实际产出。\n"
            "2. 工具按需调用：根据用户实际需求在恰当时机主动调用挂载的工具；严禁在输出中泄露内部思考痕迹或参数代码。"
        )

    return "\n".join(lines)


def build_messages(
    system_prompt: str | None, history: list[dict] | None, user_message: str
) -> list[dict]:
    """组装 [system, ...history, user]; 自动剔除内容为空的历史项。"""
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    for h in (history or []):
        content = (h.get("content") or "").strip()
        if content:
            messages.append({"role": h.get("role", "user"), "content": content})
    if user_message and user_message.strip():
        messages.append({"role": "user", "content": user_message.strip()})
    return messages
