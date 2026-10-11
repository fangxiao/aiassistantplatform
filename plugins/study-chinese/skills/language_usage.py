"""语言文字运用:成语、病句、连贯表达等基础题的方法与练习。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_language_usage",
    version="0.1.0",
    description="语言文字运用:成语辨析、病句修改、表达连贯等基础题的方法讲解与练习",
    schema={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "要学的题型(如:病句六大类型)或粘贴的题目"},
        },
        "required": ["question"],
    },
    prompt=(
        "你是上海高中语文老师,处理语言文字运用题:「{{question}}」。\n"
        "若问**方法**:讲清该题型的判断框架(如病句:语紧缩主干→看搭配/残缺/语序/杂糅),"
        "每类给一个典型病句与修改,再给 2 道练习置底附答案;\n"
        "若给的是**具体题目**:先给答案,再逐项拆解为什么对为什么错,最后归纳这类题的通用判断口诀。\n"
        "例子必须是语言学界通行的规范用例(如\"他的父亲做医生的\"式经典病句),不编造生僻搭配。"
    ),
)
class LanguageUsageSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
