"""错题录入:用户描述错题 → 调工具落库;缺关键字段时用表单收齐。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_mistakes_entry",
    version="0.1.0",
    description="录入错题到错题本:用户提供题目、自己的错解、正确答案与错因后入库,并告知复习计划",
    schema={
        "type": "object",
        "properties": {
            "detail": {"type": "string", "description": "学生描述的错题内容(题面/错解/正解/错因,能提取多少是多少)"},
        },
        "required": ["detail"],
    },
    prompt=(
        "处理错题录入请求:「{{detail}}」。\n"
        "【先判断意图】若 detail 只是打招呼/闲聊/问你能干什么(如\"你好\"\"你是谁\"),"
        "严禁调用工具、严禁弹任何表单:直接用两三句文本自我介绍——你可以帮学生录入错题、"
        "按记忆曲线安排每日复习、汇总学情——并引导学生把错题发给你(拍题或手打都行)。\n"
        "确属录入意图时,再走以下流程:\n"
        "1. 从描述中提取字段:subject(数学/语文/英语/物理…)、topic(章节/知识点,可空)、"
        "question(题面,完整转写)、wrong_answer(学生自己的错解,没有就写\"未作答\")、"
        "correct_answer(正确答案,学生没给就留空并如实说明)、cause(错因,学生没说就写\"待补充\")。\n"
        "2. 调用 tool:study_mistakes_book(action=add)入库。\n"
        "3. question 与 subject 缺一不可:缺了不要自己编,用 output_block 的 input.form 一次性向学生收集缺失字段;\n"
        "4. 转写题面时保持原意,不擅自简化条件;\n"
        "5. 【必须先调工具再回复】拿到工具返回后,回复以工具返回的 message 为准——"
        "其中含「已录入错题本(第N轮)」与确定的下次复习日期,原样引用;严禁自己编造复习日期;\n"
        "6. 再补一行一句话订正建议;除此之外不要输出长篇讲解(学生要讲解会另问)。"
    ),
)
class MistakeEntrySkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
