"""每日复习:取今日到期错题,生成带题复现的复习卷。"""
from typing import Any

from agentplatform.sdk import Context, Skill, skill


@skill(
    id="skill:study_mistakes_daily_review",
    version="0.1.0",
    description="取今日到期错题,按学科分组生成复习卷;学生作答后按对错调用工具回炉或进阶",
    schema={
        "type": "object",
        "properties": {
            "grade_feedback": {
                "type": "string",
                "description": "可选:学生的作答情况(如\"第1题对,第2题错\"),用于调用 grade 回炉/进阶",
            },
        },
        "required": [],
    },
    prompt=(
        "处理每日错题复习。\n"
        "第一步【必须执行,不可跳过】:调用 tool:study_mistakes_book(action=due)。"
        "是否到期、有几题,一律以工具返回为准——严禁凭猜测直接回答「无到期错题」。\n"
        "学生的作答反馈(可能为空,为空则按无反馈流程走):{{grade_feedback}}\n"
        "工具返回 0 题:只回复一行「今日无到期错题,好好休息!」,不要长篇。\n"
        "取到题:按学科分组生成复习卷,每题复现完整题面(不要直接展示 stored 的正确答案),"
        "题末留作答空间;卷末统一附「核对区」,给每题的 正确答案/错因回顾/考点一句话。\n"
        "若学生已反馈作答情况:按对应 mistake_id 逐题调用 action=grade(correct=对/错),"
        "汇总每题的进阶/回炉结果与明日到期数。\n"
        "严禁泄露 stage/next_review_at 等内部字段;严禁编造工具未返回的错题。"
    ),
)
class DailyReviewSkill(Skill):
    def execute(self, ctx: Context, args: dict[str, Any]) -> str:
        return self.render(args)
