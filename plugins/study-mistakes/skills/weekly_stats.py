"""学情汇总:近一周错题分布与复习完成情况(供学情周报定时任务)。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_mistakes_weekly_stats",
    version="0.1.0",
    description="汇总近一周错题:学科/知识点分布、错因TOP、复习完成情况与下周建议,供学情周报推送",
    schema={
        "type": "object",
        "properties": {},
    },
    prompt=(
        "生成近一周学情汇总。先调用 tool:study_mistakes_book(action=list)取全部错题"
        "(≤50 条),在结果里按 created_at/last_graded_at 自行筛出近 7 天的记录。\n"
        "输出 markdown,按序:\n"
        "1. **本周概览**:新录入 N 道、完成复习 M 次,一行;\n"
        "2. **学科分布**:表格(学科/条数/占比),无数据的学科不列;\n"
        "3. **错因 TOP**:按 cause 出现次数列前 3,各附一条对应题目做个例提醒;\n"
        "4. **复习状态**:到期未复习的条数(如有,提醒先清账);\n"
        "5. **下周建议**:1-2 条,基于数据说,不空泛。\n"
        "错题总数为 0 时回复固定一行「本周错题本空空如也,继续保持!」即可。数字必须来自工具返回,严禁估算。"
    ),
)
class WeeklyStatsSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
