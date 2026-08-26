"""内置资源测试:元信息合法性、prompt 模板、seed 登记。"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.builtin import (
    ALL,
    cross_document_compare,
    html_cleaner,
    structured_output,
    summarize,
)
from agentplatform.core.registry.service import resolve, seed_builtin


class TestResourceMetadata:
    def test_all_builtins_well_formed(self) -> None:
        assert len(ALL) == 5
        for res in ALL:
            assert res["id"].startswith(("tool:", "skill:"))
            assert res["kind"] in {"tool", "skill"}
            assert res["name"]
            assert res["version"].count(".") == 2
            assert "parameters" in res["schema"]

    def test_ids_unique(self) -> None:
        ids = [r["id"] for r in ALL]
        assert len(ids) == len(set(ids))


class TestPromptBuilders:
    def test_summarize_fills_params(self) -> None:
        prompt = summarize.build_prompt("很长的一段文字", style="concise", max_words=50)
        assert "很长的一段文字" in prompt
        assert "concise" in prompt
        assert "50" in prompt

    def test_structured_output_embeds_schema(self) -> None:
        prompt = structured_output.build_prompt(
            "提取字段", {"type": "object", "properties": {"a": {"type": "string"}}}, "输入"
        )
        assert '"a"' in prompt
        assert "提取字段" in prompt


class TestSeedBuiltin:
    async def test_seed_registers_all(self, session: AsyncSession) -> None:
        count = await seed_builtin(session)
        assert count == len(ALL)
        for res in ALL:
            row = await resolve(session, res["id"])
            assert row is not None
            assert row.version == res["version"]
            assert row.source.value == "builtin"

    async def test_seed_is_idempotent(self, session: AsyncSession) -> None:
        await seed_builtin(session)
        await seed_builtin(session)
        assert await resolve(session, "skill:summarize") is not None


class TestHtmlCleaner:
    def test_strips_scripts_and_styles(self) -> None:
        html = """
        <html><head><title>测试页</title></head><body>
        <script>var x = 1;</script>
        <style>.hidden{display:none}</style>
        <p>这是正文内容。</p>
        </body></html>
        """
        result = json.loads(html_cleaner.run(html))
        assert result["title"] == "测试页"
        assert "这是正文内容" in result["cleaned_markdown"]
        assert "var x" not in result["cleaned_markdown"]
        assert ".hidden" not in result["cleaned_markdown"]

    def test_extracts_tables(self) -> None:
        html = """
        <table>
          <tr><th>名称</th><th>价格</th></tr>
          <tr><td>基础版</td><td>免费</td></tr>
          <tr><td>专业版</td><td>99元/月</td></tr>
        </table>
        """
        result = json.loads(html_cleaner.run(html, extract_tables=True))
        assert result["metadata"]["table_count"] == 1
        table = result["tables_json"][0]
        assert table["has_header"] is True
        assert table["header"] == ["名称", "价格"]
        assert table["rows"] == [["基础版", "免费"], ["专业版", "99元/月"]]

    def test_markdown_conversion(self) -> None:
        html = """
        <h1>标题一</h1>
        <p>第一段 <strong>加粗</strong> 和 <a href="https://example.com">链接</a></p>
        """
        result = json.loads(html_cleaner.run(html))
        md = result["cleaned_markdown"]
        assert "标题一" in md
        assert "加粗" in md
        assert "example.com" in md

    def test_no_tables_when_disabled(self) -> None:
        html = "<table><tr><td>a</td></tr></table>"
        result = json.loads(html_cleaner.run(html, extract_tables=False))
        assert result["tables_json"] == []


class TestCrossDocumentCompare:
    def test_prompt_includes_all_entities_and_dimensions(self) -> None:
        entities = [
            {"name": "Notion", "content": "All-in-one workspace, 免费/专业版"},
            {"name": "飞书", "content": "办公协作套件, 企业版按年付费"},
        ]
        dimensions = ["功能覆盖", "价格模式"]
        prompt = cross_document_compare.build_prompt(entities, dimensions)

        assert "[Notion]" in prompt
        assert "[飞书]" in prompt
        assert "- 功能覆盖" in prompt
        assert "- 价格模式" in prompt
        assert "comparison_matrix" in prompt
        assert "summary_markdown" in prompt

    def test_prompt_requires_entities_and_dimensions(self) -> None:
        res = cross_document_compare.RESOURCE
        required = res["schema"]["parameters"]["required"]
        assert required == ["entities", "dimensions"]
