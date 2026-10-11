"""古代诗歌鉴赏:意象、手法、情感与比较鉴赏。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_poetry_appreciation",
    version="0.1.0",
    description="古诗鉴赏:讲解单篇(意象/手法/情感)或按上海卷风格出题并给满分答案",
    schema={
        "type": "object",
        "properties": {
            "poem_or_question": {"type": "string", "description": "诗歌原文(或诗题+诗人),或要学的鉴赏方法"},
        },
        "required": ["poem_or_question"],
    },
    prompt=(
        "你是上海高中语文老师,处理古诗鉴赏:「{{poem_or_question}}」。\n"
        "两种情形:\n"
        "A. 给的是**诗歌**:按序讲解——①画面描述(用自己的话串译全诗);"
        "②意象表(意象/常见含义/在本诗中的作用);③手法(修辞/表现手法/抒情方式,各引原句);"
        "④情感(结合诗人与注释,不用套路化标签,说出具体情感);⑤上海卷考法(常考:情感概括/手法分析/比较鉴赏)。\n"
        "B. 学生问的是**方法**:讲该类题的答题框架,给 1 个满分示例与丢分反例。\n"
        "解读必须从诗句出发,每个结论标注所依据的诗句;诗人背景只在教材与通识范围内说,不编造。"
    ),
)
class PoetryAppreciationSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
