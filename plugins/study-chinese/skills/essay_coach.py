"""高考议论文教练:立意、结构、素材,针对上海高考作文。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_essay_coach",
    version="0.1.0",
    description="针对上海高考作文题:多角度立意、推荐结构、可迁移素材与段落示范",
    schema={
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "作文题或材料原文"},
            "draft": {"type": "string", "description": "可选:学生已有的立意或提纲,求点评"},
        },
        "required": ["topic"],
    },
    prompt=(
        "你是上海高中语文老师,带学生攻上海高考议论文。作文题:「{{topic}}」。\n"
        "学生已有想法(可能为空,为空则忽略):{{draft}}\n"
        "输出 markdown,按序:\n"
        "1. **审题**:材料的核心概念与隐含限制,指出最容易跑题的方向;\n"
        "2. **立意**:3 个由稳到亮的立意,每个一句话,标推荐度;\n"
        "3. **结构**:推荐一种论证结构,列出每段的功能与句数预算;\n"
        "4. **素材**:3 个可迁移素材(人物/事例/思想各一),每个写两行:事实 + 使用角度;素材必须真实可查,严禁编造名言与事迹;\n"
        "5. **开头示范**:按推荐立意写一段 100 字左右的开头。\n"
        "有学生想法时先点评再给方案。"
    ),
)
class EssayCoachSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
