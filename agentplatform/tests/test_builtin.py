"""内置资源测试:元信息合法性、prompt 模板、seed 登记。"""

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.builtin import ALL, structured_output, summarize
from agentplatform.core.registry.service import resolve, seed_builtin


class TestResourceMetadata:
    def test_all_builtins_well_formed(self) -> None:
        assert len(ALL) == 3
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
