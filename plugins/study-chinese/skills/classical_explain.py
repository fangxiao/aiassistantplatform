"""文言文精讲:篇目或原文段落的逐段讲解。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_chinese_classical_explain",
    version="0.1.0",
    description="精讲一篇文言文或一段原文:白话翻译、实词虚词、词类活用、特殊句式与考点",
    schema={
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "篇目名(如《劝学》),或粘贴的原文段落"},
        },
        "required": ["target"],
    },
    prompt=(
        "你是上海高中语文老师,精讲文言文:「{{target}}」。\n"
        "若给的是篇目名且属沪教版高中教材,按教材选文讲解;若给的是原文段落,直接讲解该段。\n"
        "输出 markdown,按序:\n"
        "1. **原文与翻译**:按自然段对照,原文一段、白话译文一段;\n"
        "2. **重点实词**:表格(词/本段义项/例句),只收本段出现的;\n"
        "3. **重点虚词**:表格(词/用法/本段例句),覆盖 而/之/以/为/则/于/者/也/乎 中本段出现的;\n"
        "4. **词类活用与特殊句式**:逐条列出并标注类型(判断/被动/宾语前置/定语后置/状语后置/省略),每条给翻译;\n"
        "5. **考点提示**:本段在上海高考文言文阅读中最可能设题的 2 个点。\n"
        "译文以直译为主;拿不准的通假字不要硬编,如实说明存疑。"
    ),
)
class ClassicalExplainSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
