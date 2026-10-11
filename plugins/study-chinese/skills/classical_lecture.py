"""每日一篇文言文讲义:按篇目生成完整学习讲义,配合定时任务每日轮换推送。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_classical_lecture",
    version="0.1.0",
    description="按篇目名生成一份完整的文言文学习讲义(原文/翻译/字词/句式/默写/考点),供每日定时推送",
    schema={
        "type": "object",
        "properties": {
            "piece": {"type": "string", "description": "今日篇目名,如《六国论》"},
            "avoid": {"type": "string", "description": "可选:近期已讲过的篇目,逗号分隔"},
        },
        "required": ["piece"],
    },
    prompt=(
        "生成今日文言文学习讲义,篇目:「{{piece}}」(沪教版高中教材范围)。\n"
        "近期已讲过、本次应避开(可能为空,为空则忽略):{{avoid}}\n"
        "输出 markdown,按序:\n"
        "## 今日篇目:{{piece}}\n"
        "1. **原文**(全文,按段分隔);2. **逐段白话翻译**;3. **高频实词 8 个**(表格:词/释义/原文例句);\n"
        "4. **虚词与句式要点**(≤5 条,标注类型);5. **名句默写**(本篇最可能考的 3 句,挖空版附后);\n"
        "6. **一段话讲清本篇在高考中的地位**。\n"
        "原文必须准确,凭记忆不确定的句子宁可标注(原文请核对课本),严禁编造。只输出讲义本体。"
    ),
)
class ClassicalLectureSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
