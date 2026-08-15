"""PRD 文档评审 Skill 定义 (设计 006 §3)。"""

from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:prd_review",
    version="1.0.0",
    description="按完整性、可行性、业务价值、潜在风险等多维度深度评审 PRD 文档",
    schema={
        "type": "object",
        "properties": {
            "doc": {"type": "string", "description": "PRD 需求文档正文或摘要"},
            "dimensions": {
                "type": "string",
                "description": "自定义评审维度，如完整性、可行性、风险",
            },
        },
        "required": ["doc"],
    },
    prompt=(
        "你是一个资深产品专家，请针对以下 PRD 内容进行专业评审：\n"
        "【评审维度】：{{dimensions}}\n"
        "【PRD 文档正文】：\n{{doc}}\n\n"
        "请给出：1. 核心亮点 2. 关键遗漏与潜在风险 3. 具体改进建议。"
    ),
)
class PRDReview(Skill):
    """PRD 评审技能实现。"""

    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        if not args.get("dimensions"):
            args["dimensions"] = "需求完整性、技术可行性、用户体验与业务风险"
        return self.render(args)
