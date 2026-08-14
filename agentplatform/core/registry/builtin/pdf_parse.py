"""tool:pdf_parse —— 解析 PDF 为纯文本(平台内置)。

确定性接口(设计 002 §2):输入文件路径,输出提取的文本。
实现按需加载 pypdf(M5 执行器接入时再正式引入该依赖),未安装时给出明确错误。
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "tool:pdf_parse",
    "kind": "tool",
    "name": "pdf_parse",
    "version": "1.0.0",
    "description": "解析 PDF 为纯文本",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "PDF 文件路径"}
            },
            "required": ["file_path"],
        },
        "returns": {"type": "string", "description": "PDF 提取出的纯文本"},
    },
}


def run(file_path: str) -> str:
    """提取 PDF 文本;pypdf 未安装时抛 RuntimeError。"""
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        raise RuntimeError(
            "pdf_parse 需要 pypdf 依赖,安装: uv add pypdf"
        ) from None
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)
