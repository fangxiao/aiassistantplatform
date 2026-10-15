"""测试用确定性 tool:回显平台注入的 ctx(身份/图片透传验证)。"""

import json


def run(text: str = "", ctx=None) -> str:
    return json.dumps(
        {
            "user_id": getattr(ctx, "user_id", None),
            "session_id": getattr(ctx, "session_id", None),
            "images": list(getattr(ctx, "images", None) or []),
        },
        ensure_ascii=False,
    )
