"""注册表服务集成测试(真实 PostgreSQL 测试库)。

PG 不可达时跳过(测试不依赖常驻基础设施);测试库独立于开发库,
建表/清表用 Base.metadata,不依赖迁移状态。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.registry.model import SkillToolKind as K
from agentplatform.core.registry.model import SkillToolSource as S
from agentplatform.core.registry.service import (
    check_dependencies,
    latest_of_each,
    list_public,
    parse_dependency,
    register,
    resolve,
    resolve_public,
    split_dependency,
)


async def _seed(session: AsyncSession) -> None:
    await register(
        session,
        resource_id="tool:pdf_parse",
        kind=K.tool,
        name="pdf_parse",
        version="1.0.0",
        source=S.builtin,
        schema_={
            "parameters": {
                "type": "object",
                "properties": {"file": {"type": "string"}},
                "required": ["file"],
            },
            "returns": {"type": "string"},
        },
        impl_path="agentplatform.core.registry.builtin.pdf_parse",
        description="解析 PDF 为文本",
    )
    await register(
        session,
        resource_id="tool:pdf_parse",
        kind=K.tool,
        name="pdf_parse",
        version="1.2.0",
        source=S.builtin,
        schema_={"parameters": {"type": "object"}, "returns": {"type": "string"}},
        impl_path="agentplatform.core.registry.builtin.pdf_parse",
        description="解析 PDF 为文本",
    )
    await register(
        session,
        resource_id="skill:summarize",
        kind=K.skill,
        name="summarize",
        version="1.0.0",
        source=S.shared,
        schema_={"parameters": {"type": "object"}, "returns": {"type": "string"}},
        impl_path="agentplatform.core.registry.builtin.summarize",
        description="摘要 skill",
    )
    await register(
        session,
        resource_id="tool:private_demo",
        kind=K.tool,
        name="private_demo",
        version="0.1.0",
        source=S.private,
        schema_={"parameters": {"type": "object"}, "returns": {"type": "string"}},
        owner_id="dev-1",
    )
    await session.commit()


class TestRegisterAndResolve:
    async def test_no_constraint_returns_latest(self, session: AsyncSession) -> None:
        await _seed(session)
        row = await resolve(session, "tool:pdf_parse")
        assert row is not None
        assert row.version == "1.2.0"

    async def test_caret_constraint(self, session: AsyncSession) -> None:
        await _seed(session)
        row = await resolve(session, "tool:pdf_parse", "^1.0")
        assert row is not None
        assert row.version == "1.2.0"
        assert await resolve(session, "tool:pdf_parse", "^2.0") is None

    async def test_exact_constraint(self, session: AsyncSession) -> None:
        await _seed(session)
        row = await resolve(session, "tool:pdf_parse", "1.0.0")
        assert row is not None
        assert row.version == "1.0.0"

    async def test_unknown_id_returns_none(self, session: AsyncSession) -> None:
        assert await resolve(session, "tool:nope") is None

    async def test_register_updates_existing(self, session: AsyncSession) -> None:
        await _seed(session)
        row = await register(
            session,
            resource_id="tool:pdf_parse",
            kind=K.tool,
            name="pdf_parse",
            version="1.2.0",
            source=S.builtin,
            schema_={"parameters": {"type": "object"}},
            description="覆盖后的描述",
        )
        await session.commit()
        assert row.description == "覆盖后的描述"
        resolved = await resolve(session, "tool:pdf_parse", "^1.0")
        assert resolved is not None
        assert resolved.version == "1.2.0"


class TestListPublic:
    async def test_filters_private_and_dedups_latest(self, session: AsyncSession) -> None:
        await _seed(session)
        rows = latest_of_each(await list_public(session))
        ids = {r.id for r in rows}
        assert ids == {"tool:pdf_parse", "skill:summarize"}
        pdf = next(r for r in rows if r.id == "tool:pdf_parse")
        assert pdf.version == "1.2.0"

    async def test_kind_filter(self, session: AsyncSession) -> None:
        await _seed(session)
        skills = latest_of_each(await list_public(session, kind=K.skill))
        assert [r.id for r in skills] == ["skill:summarize"]
        tools = latest_of_each(await list_public(session, kind=K.tool))
        assert [r.id for r in tools] == ["tool:pdf_parse"]


class TestDependencies:
    async def test_all_satisfied(self, session: AsyncSession) -> None:
        await _seed(session)
        missing = await check_dependencies(
            session, ["tool:pdf_parse@^1.0", "skill:summarize@^1.0"]
        )
        assert missing == []

    async def test_reports_missing(self, session: AsyncSession) -> None:
        await _seed(session)
        missing = await check_dependencies(
            session, ["tool:pdf_parse@^2.0", "skill:missing@^1.0"]
        )
        assert missing == ["tool:pdf_parse@^2.0", "skill:missing@^1.0"]

    def test_split_dependency(self) -> None:
        assert split_dependency("tool:pdf_parse@^1.0") == ("tool:pdf_parse", "^1.0")
        assert split_dependency("tool:pdf_parse") == ("tool:pdf_parse", None)

    def test_parse_optional_dependency(self) -> None:
        parsed = parse_dependency("tool:html_cleaner@^1.0?")
        assert parsed.resource_id == "tool:html_cleaner"
        assert parsed.constraint == "^1.0"
        assert parsed.optional is True
        assert split_dependency("tool:html_cleaner@^1.0?") == (
            "tool:html_cleaner",
            "^1.0",
        )
        assert parse_dependency("tool:pdf_parse@^1.0").optional is False

    async def test_optional_missing_does_not_block(self, session: AsyncSession) -> None:
        await _seed(session)
        # 可选依赖平台缺失 + 一个必选依赖满足 → 不报缺失
        missing = await check_dependencies(
            session,
            ["tool:pdf_parse@^1.0", "tool:html_cleaner@^1.0?"],
        )
        assert missing == []

    async def test_private_resource_does_not_satisfy_required(self, session: AsyncSession) -> None:
        await register(
            session,
            resource_id="tool:only_private",
            kind=K.tool,
            name="only_private",
            version="2.0.0",
            source=S.private,
            schema_={"parameters": {"type": "object"}},
            description="他人插件私有工具",
        )
        await session.commit()
        # 必选依赖:其他插件的私有资源不算满足
        missing = await check_dependencies(session, ["tool:only_private@^2.0"])
        assert missing == ["tool:only_private@^2.0"]
        assert await resolve_public(session, "tool:only_private") is None

    async def test_resolve_prefers_public_over_higher_private(
        self, session: AsyncSession
    ) -> None:
        """同名资源:平台公共版优先,即使私有实现版本号更高(T11.10 回退基础)。"""
        await register(
            session,
            resource_id="tool:html_cleaner",
            kind=K.tool,
            name="html_cleaner",
            version="1.0.0",
            source=S.builtin,
            schema_={"parameters": {"type": "object"}},
            description="平台版",
        )
        await register(
            session,
            resource_id="tool:html_cleaner",
            kind=K.tool,
            name="html_cleaner",
            version="2.5.0",
            source=S.private,
            schema_={"parameters": {"type": "object"}},
            description="插件本地回退实现(更高版本号也不能顶掉平台版)",
        )
        await session.commit()
        resolved = await resolve(session, "tool:html_cleaner")
        assert resolved is not None
        assert resolved.source == S.builtin
        assert resolved.version == "1.0.0"

    async def test_resolve_falls_back_to_private_when_public_absent(
        self, session: AsyncSession
    ) -> None:
        """平台无公共版时,resolve 回退到插件本地同名实现。"""
        await register(
            session,
            resource_id="tool:html_cleaner",
            kind=K.tool,
            name="html_cleaner",
            version="0.9.0",
            source=S.private,
            schema_={"parameters": {"type": "object"}},
            description="插件本地回退实现",
        )
        await session.commit()
        resolved = await resolve(session, "tool:html_cleaner", "^0.9")
        assert resolved is not None
        assert resolved.source == S.private
        assert resolved.version == "0.9.0"
