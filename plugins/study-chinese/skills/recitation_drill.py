"""默写训练:按篇目生成理解性默写挖空题,配合定时任务每日一练。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_recitation_drill",
    version="0.1.0",
    description="按篇目范围生成理解性默写与挖空填空训练题,答案置底,供每日定时推送",
    schema={
        "type": "object",
        "properties": {
            "scope": {"type": "string", "description": "篇目范围,如:《劝学》《师说》 / 必修上全部古诗文的含\"月\"句"},
        },
        "required": ["scope"],
    },
    prompt=(
        "生成今日默写训练,范围:「{{scope}}」(沪教版高中必背篇目)。\n"
        "出 6 题,两类混合:\n"
        "1. **理解性默写**(4 题):给内容理解,填原句,如\"《劝学》中强调积累重要性的句子是____\";\n"
        "2. **情境挖空**(2 题):给出上下文句,挖空关键字词,易错字用( )提示字数。\n"
        "之后用分隔线隔开,附「参考答案与易错字提醒」:每题答案 + 该句最容易写错的字(如\"輮\"\"槁暴\")。\n"
        "只考必背篇目与真实原句,严禁编造教材中不存在的句子。只输出题目与答案本体。"
    ),
)
class RecitationDrillSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
