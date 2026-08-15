"""PRD 质量评分 Tool 定义 (设计 006 §4)。"""

import json

from agentplatform.sdk import tool


@tool(
    id="tool:prd_score",
    version="1.0.0",
    description="对 PRD 文本进行确定性质量与完整度综合打分 (0-100分)",
    schema={
        "type": "object",
        "properties": {
            "doc": {"type": "string", "description": "PRD 文档内容"},
        },
        "required": ["doc"],
    },
)
def prd_score(doc: str = "") -> str:
    """计算 PRD 文档质量得分并返回分项指标。"""
    text = doc or ""
    length = len(text)

    # 简易启发式评分算法
    clarity_score = min(30, max(5, int(length / 10)))
    has_goals = (
        25 if any(k in text for k in ["目标", "背景", "goal", "background"]) else 10
    )
    has_user_stories = (
        25 if any(k in text for k in ["用户", "场景", "user", "flow"]) else 10
    )
    has_metrics = (
        20 if any(k in text for k in ["指标", "验收", "metric", "acceptance"]) else 5
    )

    total = clarity_score + has_goals + has_user_stories + has_metrics
    score = min(100, max(0, total))

    grade = "优秀 (A)" if score >= 85 else "良好 (B)" if score >= 70 else "需完善 (C)"

    result = {
        "total_score": score,
        "metrics": {
            "clarity_and_detail": clarity_score,
            "goal_definition": has_goals,
            "user_scenario": has_user_stories,
            "success_metrics": has_metrics,
        },
        "grade": grade,
    }
    return json.dumps(result, ensure_ascii=False)
