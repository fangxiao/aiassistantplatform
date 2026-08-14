"""测试用确定性 tool 实现:echo,无需外部依赖。"""


def run(text: str) -> str:
    """把输入转为大写返回。"""
    return text.upper()
