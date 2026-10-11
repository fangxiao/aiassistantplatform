"""词汇精讲:面向上海高考英语的单词深度讲解。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_english_vocab_explain",
    version="0.1.0",
    description="讲解一个英语单词或短语:音标、词义、高频搭配、近义辨析与高考语境例句",
    schema={
        "type": "object",
        "properties": {
            "word": {"type": "string", "description": "要讲解的单词或短语"},
            "context": {"type": "string", "description": "可选:学生遇到该词的句子或语境"},
        },
        "required": ["word"],
    },
    prompt=(
        "你是上海高中英语老师,面向上教版教材与上海高考,精讲单词「{{word}}」。\n"
        "学生补充的出现语境(可能为空,为空则忽略本行):{{context}}\n"
        "按以下结构输出 markdown:\n"
        "1. **发音**:英式音标,多音节词标注重音,易读错的音节给汉字拟音提示;\n"
        "2. **词义与词性**:按词性分行,只收高考范围义项,生僻义不展开;\n"
        "3. **高频搭配**:3-4 个,每个配一句高考难度例句并附中文译文;\n"
        "4. **近义辨析**:与 1-2 个易混词对比,用表格(词/核心区别/典型搭配);\n"
        "5. **记法**:词根词缀或联想一句话。\n"
        "全部用中文讲解、英文例句;不确定的语料宁缺毋滥,不要编造真题出处。"
    ),
)
class VocabExplainSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
