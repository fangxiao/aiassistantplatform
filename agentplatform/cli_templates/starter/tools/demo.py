"""插件确定性工具 (Tool):执行确定性的 Python 计算/转换/外部调用。"""
import json

from agentplatform.sdk import tool


@tool(
    id="tool:{plugin_name}_echo",
    version="0.1.0",
    description="回显与简单格式化工具",
    schema={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "输入文本"}},
        "required": ["text"],
    },
)
def echo(text: str) -> str:
    """回显输入文本。"""
    return json.dumps({"status": "success", "echo": text}, ensure_ascii=False)
