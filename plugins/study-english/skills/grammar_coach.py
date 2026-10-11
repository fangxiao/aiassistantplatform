"""语法答疑与句子纠错:讲规则、改病句、配练习。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_english_grammar_coach",
    version="0.1.0",
    description="讲解语法规则或批改英语句子:逐条指出问题、给出改后句子并配即时练习",
    schema={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "语法疑问,或需要批改的一个/多个句子"},
        },
        "required": ["question"],
    },
    prompt=(
        "你是上海高中英语老师,处理学生的语法问题:「{{question}}」。\n"
        "若问的是语法规则:用 2-3 段讲清核心规则,给 2 个正例 1 个反例,再说明上海高考中它的常见考法。\n"
        "若发来的是句子求批改:先用表格逐句输出(原句 | 问题 | 改后 | 依据的语法点),"
        "只改真正的错误,不重写风格;然后针对暴露的薄弱语法点出 3 道单句改错或填空练习,"
        "答案与解析放在最后的「参考答案」小节,方便学生先做后对。\n"
        "用中文讲解,例句保留英文。"
    ),
)
class GrammarCoachSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
