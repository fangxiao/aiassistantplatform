"""示例插件:PRD 评审 skill(006 §3 定义形态)。

M4 只登记元信息;代码加载与执行在 M5/SDK(M9)接入后启用。
此处给出与 006 一致的示意实现,供后续里程碑对齐。
"""

# from agentplatform.sdk import Skill, skill  # M9 SDK 引入后启用

PROMPT = (
    "你是一个 PRD 评审专家,请按以下维度评审:{{dimensions}}。"
    "基于文档:\n{{doc}}"
)


def render(args: dict) -> str:
    """简单 skill:填充 prompt 模板(M5 执行器会调用)。"""
    dimensions = args.get("dimensions", "完整性、可行性、优先级、风险")
    doc = args.get("doc", "")
    return PROMPT.format(dimensions=dimensions, doc=doc)
