"""知识点精讲:沪教版数学概念的讲解与典型例题。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_math_concept_explain",
    version="0.1.0",
    description="讲解一个数学知识点:定义、公式推导、典型例题分步解析与易错点",
    schema={
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "知识点,如:函数的单调性 / 圆锥曲线的第二定义"},
            "chapter": {"type": "string", "description": "可选:教材章节,如必修一第三章"},
        },
        "required": ["topic"],
    },
    prompt=(
        "你是上海高中数学老师,讲解知识点:「{{topic}}」(沪教版{{chapter}})。\n"
        "输出 markdown,按序:\n"
        "1. **它是什么**:一两句话给出定义,再用一个生活化类比让学生有画面;\n"
        "2. **核心公式与推导**:公式列全,关键一步推导写过程而非只给结论;\n"
        "3. **典型例题**:2 道由易到难,每题分步写,每步标注依据(定义/定理/法则);\n"
        "4. **易错点**:3 条,每条给一个错误示范与纠正;\n"
        "5. **高考怎么考**:上海卷常见题型与分值量级,一句话。\n"
        "数学式子用标准记法;上海高考不分文理、选择填空占比高,例题贴近该风格。"
    ),
)
class ConceptExplainSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
