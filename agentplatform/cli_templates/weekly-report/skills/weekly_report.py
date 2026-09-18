"""周报生成技能:把零散工作要点整理为结构化周报。

改这里:调整周报的栏目结构/语气/侧重点。
"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:{plugin_name}_weekly_report",
    version="0.1.0",
    description="把本周工作要点整理为结构化周报(本周进展/风险/下周计划)",
    schema={
        "type": "object",
        "properties": {
            "highlights": {"type": "string", "description": "本周工作要点,每行一条"},
            "audience": {
                "type": "string",
                "enum": ["team", "manager", "client"],
                "description": "汇报对象,决定语气与详略",
            },
        },
        "required": ["highlights"],
    },
    prompt=(
        "你是专业的项目管理助手。请把以下本周工作要点整理为一份周报,"
        "结构为:①本周进展(按事项分组,突出结果而非过程);②风险与阻塞;"
        "③下周计划。汇报对象是 {{audience}},相应调整语气与详略。\n\n"
        "工作要点:\n{{highlights}}"
    ),
)
class WeeklyReportSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        if not args.get("audience"):
            args["audience"] = "team"
        return self.render(args)
