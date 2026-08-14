"""SSE 事件格式化(设计 005 §4 / 003 v2.0 §3.3)。

帧格式:event: <type>\ndata: <json>\n\n
"""

import json


def sse(event: str, data: dict) -> str:
    """格式化为一条 SSE 帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
