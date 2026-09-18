"""文档摘要问答技能:引导 kb_search 检索并结构化输出。

改这里:调整摘要的维度与输出格式。
"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:{plugin_name}_summarize_doc",
    version="0.1.0",
    description="对知识库中的文档生成摘要并支持追问",
    schema={
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "要总结的主题或问题"},
        },
        "required": ["topic"],
    },
    prompt=(
        "你是文档分析助手。请先用 kb_search 检索与「{{topic}}」相关的资料,"
        "然后输出:①一段 150 字以内的摘要;②三个关键要点;③资料来源文档名。"
        "若检索无结果,如实告知并建议用户补充资料。"
    ),
)
class SummarizeDocSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
