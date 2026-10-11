"""现代文阅读:论述类与文学类,按题型讲方法、按文段做练习。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_modern_reading",
    version="0.1.0",
    description="现代文阅读(论述类/文学类):题型方法讲解,或对给定文段出题并给参考答案",
    schema={
        "type": "object",
        "properties": {
            "passage_or_question": {
                "type": "string",
                "description": "学生粘贴的文段/题目,或要学的题型(如:作用题怎么答)",
            },
            "genre": {"type": "string", "description": "文体:论述类 / 文学类(散文·小说),不确定可留空"},
        },
        "required": ["passage_or_question"],
    },
    prompt=(
        "你是上海高中语文老师,处理现代文阅读:「{{passage_or_question}}」(文体:{{genre}},未指明则自行判断)。\n"
        "两种情形:\n"
        "A. 学生问的是**题型方法**:讲清该题型的答题框架(上海高考评分习惯:分点+结合文本),"
        "给 1 个典型例题与满分答案示例,再点出最常见的丢分写法;\n"
        "B. 学生给的是**文段求练习**:从该文段命 2-3 道符合上海卷风格的理解/作用/含义/比较题,"
        "题目之后附参考答案与得分点拆解(标注哪一句文本是得分依据),答案与题目之间用分隔线隔开。\n"
        "解读文本必须基于原文原句,禁止脱离文本套模板空答;答案里的每个得分点都要能落到具体语句。"
    ),
)
class ModernReadingSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
