"""每日词汇清单:按指定范围生成 10 词学习集,配合定时任务每日推送。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_english_daily_vocab_set",
    version="0.1.0",
    description="按教材单元或词表范围生成今日 10 词学习清单(释义+搭配+例句),供每日定时推送",
    schema={
        "type": "object",
        "properties": {
            "scope": {"type": "string", "description": "词汇范围,如:上教版必修一 Unit 3 / 高考核心动词第 2 组"},
            "avoid": {"type": "string", "description": "可选:近期已学过、本次要避开的词,逗号分隔"},
        },
        "required": ["scope"],
    },
    prompt=(
        "生成今日上海高中英语词汇学习清单,范围:「{{scope}}」。\n"
        "近期已学过、本次必须避开的词(可能为空,为空则不回避):{{avoid}}\n"
        "选 10 个高考高频词,难易梯度 3:4:3(基础:中档:进阶),输出 markdown:\n"
        "## 今日词汇({{scope}})\n"
        "每词一条:**word** /音标/ 词性 + 核心义(一行)/ 高频搭配一例(英文+中文)/ 一词一句助记。\n"
        "结尾加「自测」小节:10 个中文释义乱序列出,让学生回填英文。\n"
        "只输出清单本体,不要开场白。"
    ),
)
class DailyVocabSetSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
