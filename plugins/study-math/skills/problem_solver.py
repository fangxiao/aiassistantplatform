"""规范化解题:审题、思路、分步详解、易错提醒与变式。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_math_problem_solver",
    version="0.1.0",
    description="解一道数学题:先给思路再分步详解,每步标注依据,并给一道变式训练",
    schema={
        "type": "object",
        "properties": {
            "problem": {"type": "string", "description": "题目原文;若是拍照题,写照片中题目的转述"},
            "my_attempt": {"type": "string", "description": "可选:学生自己的尝试或卡住的位置"},
        },
        "required": ["problem"],
    },
    prompt=(
        "解这道数学题:「{{problem}}」。\n"
        "学生自己的尝试(可能为空,为空则忽略):{{my_attempt}}\n"
        "严格按序输出 markdown:\n"
        "1. **审题**:已知/未知/隐含条件各一行;\n"
        "2. **思路**:先说清通向答案的路径选择(为什么走这条路,备选路径为何不走);\n"
        "3. **详解**:分步编号,每步右侧用括号标注依据;运算写关键中间量,不跳步;\n"
        "4. **检查**:代入或特殊值验证一句话;\n"
        "5. **易错提醒**:本题最容易错的一步;\n"
        "6. **变式**:同考点换一个数字/情境的变式题,只给题目不给答案。\n"
        "有学生尝试时,先指出卡在哪一步、对在哪里,再给完整详解。"
    ),
)
class ProblemSolverSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
