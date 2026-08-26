"""tool:html_cleaner —— 网页正文/DOM 语义提取(平台内置)。

RFC-2026-001 §RFC-1:HTML 去噪 + Markdown 转换 + 表格结构化提取。
基于 readability-lxml 或纯 Python 启发式算法实现。
"""

from agentplatform.core.registry.builtin.meta import ResourceMeta

RESOURCE: ResourceMeta = {
    "id": "tool:html_cleaner",
    "kind": "tool",
    "name": "html_cleaner",
    "version": "1.0.0",
    "description": "解析 HTML 正文为 Markdown，支持表格结构化提取",
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "html_content": {
                    "type": "string",
                    "description": "原始 HTML 或 DOM 片段",
                },
                "extract_tables": {
                    "type": "boolean",
                    "description": "是否专门结构化提取表格数据",
                },
            },
            "required": ["html_content"],
        },
        "returns": {
            "type": "object",
            "description": "title / cleaned_markdown / tables_json / metadata",
        },
    },
}

# 纯 Python 启发式去噪:移除 script/style/注释/无用标签,提取正文
_REMOVE_TAGS = frozenset({
    "script", "style", "noscript", "iframe", "svg", "canvas",
    "video", "audio", "source", "track", "meta", "link",
    "object", "embed", "param", "applet",
})

_BLOCK_TAGS = frozenset({
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "blockquote", "pre", "hr",
    "table", "tr", "td", "th", "thead", "tbody", "tfoot",
    "section", "article", "nav", "header", "footer", "main",
    "figure", "figcaption", "details", "summary",
})


def _clean_html(html: str) -> tuple[str, str]:
    """极简 HTML 去噪:去除标签属性和 REMOVE_TAGS,保留文本。

    返回 (title, cleaned_html)。不依赖第三方库,兼容无法安装 readability 的环境。
    """
    import re

    # 1. 移除注释
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

    # 2. 移除有害标签及其内容
    for tag in _REMOVE_TAGS:
        html = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "",
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # 3. 提取 <title>
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    return title, html


def _html_to_markdown(html: str) -> str:
    """将干净的 HTML 正文转换为近似 Markdown (无外部依赖的启发式版本)。"""
    import re

    text = html

    # 先处理链接与图片(保留 href/src),再剥其余标签
    def _link_repl(m: re.Match[str]) -> str:
        href = m.group("href")
        label = re.sub(r"<[^>]+>", "", m.group("label")).strip()
        return f"[{label}]({href})" if href else label

    text = re.sub(
        r"<a[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>",
        _link_repl,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def _img_repl(m: re.Match[str]) -> str:
        src = m.group("src")
        alt = m.group("alt") or ""
        return f"![{alt}]({src})" if src else ""

    text = re.sub(
        r"<img[^>]*src=[\"'](?P<src>[^\"']+)[\"'][^>]*>",
        _img_repl,
        text,
        flags=re.IGNORECASE,
    )

    # 替换块级标签为换行
    for tag in _BLOCK_TAGS:
        text = re.sub(rf"</?{tag}[^>]*>", "\n", text, flags=re.IGNORECASE)

    # <br> -> 换行
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)

    # 移除残留标签
    text = re.sub(r"<[^>]+>", "", text)

    # 解码常见实体
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

    # 压缩多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


def _extract_tables(html: str) -> list[dict]:
    """从 HTML 中提取 <table> 为结构化列表(无外部依赖的启发式版本)。"""
    import re

    tables: list[dict] = []
    table_pattern = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)

    for table_match in table_pattern.finditer(html):
        table_html = table_match.group(1)
        rows: list[list[str]] = []

        # 提取所有 <tr>
        for tr_match in re.finditer(
            r"<tr[^>]*>(.*?)</tr>", table_html, re.IGNORECASE | re.DOTALL
        ):
            tr_html = tr_match.group(1)
            cells: list[str] = []

            # 提取 <th> 或 <td>
            for cell_match in re.finditer(
                r"<(?:th|td)[^>]*>(.*?)</(?:th|td)>",
                tr_html,
                re.IGNORECASE | re.DOTALL,
            ):
                cell_text = re.sub(r"<[^>]+>", "", cell_match.group(1))
                cell_text = (
                    cell_text.replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&nbsp;", " ")
                    .strip()
                )
                cells.append(cell_text)

            if cells:
                rows.append(cells)

        has_header = False
        header_row: list[str] = []
        if rows:
            # 启发式:第一个 <tr> 全是 <th> 则视为表头
            first_tr = re.search(
                r"<tr[^>]*>(.*?)</tr>", table_html, re.IGNORECASE | re.DOTALL
            )
            if first_tr and re.search(
                r"<th", first_tr.group(1), re.IGNORECASE
            ):
                has_header = True
                header_row = rows[0]
                rows = rows[1:]

        tables.append({
            "has_header": has_header,
            "header": header_row,
            "rows": rows,
        })

    return tables


def run(html_content: str, extract_tables: bool = True) -> str:
    """执行 HTML 正文提取,返回 JSON 字符串。

    Args:
        html_content: 原始 HTML 字符串
        extract_tables: 是否提取表格

    Returns:
        JSON: {"title", "cleaned_markdown", "tables_json", "metadata"}
    """
    import json

    title, cleaned = _clean_html(html_content)
    cleaned_markdown = _html_to_markdown(cleaned)
    tables = _extract_tables(cleaned) if extract_tables else []

    # 统计
    word_count = len(cleaned_markdown.split())
    char_count = len(cleaned_markdown)

    return json.dumps(
        {
            "title": title,
            "cleaned_markdown": cleaned_markdown,
            "tables_json": tables,
            "metadata": {
                "word_count": word_count,
                "char_count": char_count,
                "table_count": len(tables),
            },
        },
        ensure_ascii=False,
    )