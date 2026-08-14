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
    register,
    resolve,
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
