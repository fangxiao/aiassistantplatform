"""插件领域技能 (Skill):修改本文件的提示词与参数,定义你的助手能力。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:{plugin_name}_demo",
    version="0.1.0",
    description="示例领域技能:智能分析与结构化建议输出",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户输入的咨询或分析需求"},
        },
        "required": ["query"],
    },
    prompt="你是一个领域专家,请针对以下内容提供专业分析:\n{{query}}",
)
class DemoSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
