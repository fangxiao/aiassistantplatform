"""每日一题:按知识点范围与难度生成练习题,配合定时任务每日推送。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_math_daily_problem",
    version="0.1.0",
    description="按知识点范围与难度生成今日一题(题面+考点+详解置底),供每日定时推送",
    schema={
        "type": "object",
        "properties": {
            "scope": {"type": "string", "description": "知识点范围,如:数列 / 立体几何 / 三角比"},
            "difficulty": {"type": "string", "description": "难度:基础 / 中档 / 压轴,默认中档"},
            "avoid": {"type": "string", "description": "可选:近期出过的题目要点,避免重复"},
        },
        "required": ["scope"],
    },
    prompt=(
        "生成今日数学一题,范围:「{{scope}}」,难度:「{{difficulty}}」(上海高考风格)。\n"
        "近期出过、应避免重复的考点(可能为空,为空则忽略):{{avoid}}\n"
        "输出 markdown,按序:\n"
        "## 今日一题({{scope}} · {{difficulty}})\n"
        "1. **题目**:题面完整、条件自洽、答案可求;\n"
        "2. **考点**:一句话;\n"
        "3. **详解**:放最后,前用「---」分隔并标注「先自己做完再看」;分步写,每步标注依据;\n"
        "4. **答案**:单独一行,放在题面与详解之间,方便先对结果。\n"
        "数值自己算一遍确认自洽,严禁出无解或矛盾题。只输出本体。"
    ),
)
class DailyProblemSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
