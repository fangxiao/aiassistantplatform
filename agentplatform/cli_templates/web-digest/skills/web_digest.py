"""网页日报技能:检索 + 抓取内容的摘要整理。

改这里:调整日报的栏目与关注领域。
"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:{plugin_name}_web_digest",
    version="0.1.0",
    description="围绕给定领域,结合联网搜索与网页内容生成摘要日报",
    schema={
        "type": "object",
        "properties": {
            "domain": {"type": "string", "description": "关注的领域或关键词"},
            "extra_urls": {"type": "string", "description": "可选,补充要总结的网页 URL,每行一个"},
        },
        "required": ["domain"],
    },
    prompt=(
        "你是资讯整理助手。请围绕「{{domain}}」:①用 web_search 检索最新动态;"
        "②若用户给了网页(extra_urls),对每个网页先 html_cleaner 提取正文再总结;"
        "③输出 5 条以内的要点日报,每条附来源链接。没有搜索服务时,基于已有知识并注明局限。"
    ),
)
class WebDigestSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
