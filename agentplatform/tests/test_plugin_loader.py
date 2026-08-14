"""插件加载器测试:清单校验、依赖解析、登记、卸载。"""

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.core.plugin.errors import DependencyError, PluginValidationError
from agentplatform.core.plugin.loader import (
    deploy_plugin,
    get_plugin,
    uninstall_plugin,
    validate_manifest,
)
from agentplatform.core.plugin.manifest import PluginManifest, ResourceDef
from agentplatform.core.registry.model import SkillTool, SkillToolSource
from agentplatform.core.registry.service import seed_builtin


def _manifest(**overrides: Any) -> PluginManifest:
    data: dict[str, Any] = {
        "name": "prd-review-assistant",
        "version": "0.1.0",
        "description": "PRD 文档评审助手",
        "model": "glm-5.2",
        "depends_on": ["tool:pdf_parse@^1.0", "skill:summarize@^1.0"],
        "skills": [
            ResourceDef(
                id="skill:prd_review",
                file="./skills/prd_review.py",
                schema={"parameters": {"type": "object"}},
            )
        ],
        "tools": [],
    }
    data.update(overrides)
    return PluginManifest(**data)


class TestValidateManifest:
    def test_ok(self) -> None:
        validate_manifest(_manifest())  # 不抛即通过

    @pytest.mark.parametrize(
        "bad", [{"name": " "}, {"version": "not-a-semver"}, {"version": "1.2"}]
    )
    def test_bad_raises(self, bad: dict) -> None:
        with pytest.raises(PluginValidationError):
            validate_manifest(_manifest(**bad))

    def test_wrong_id_prefix_raises(self) -> None:
        with pytest.raises(PluginValidationError):
            validate_manifest(
                _manifest(skills=[ResourceDef(id="tool:oops", file="./s.py")])
            )


class TestDeployPlugin:
    async def test_deploy_registers_plugin_and_resources(self, session: AsyncSession) -> None:
        await seed_builtin(session)
        plugin = await deploy_plugin(session, _manifest())
        await session.commit()

        assert plugin.name == "prd-review-assistant"
        rows = await session.scalars(
            select(SkillTool).where(SkillTool.owner_id == plugin.name)
        )
        res = list(rows)
        assert len(res) == 1
        assert res[0].id == "skill:prd_review"
        assert res[0].kind.value == "skill"
        assert res[0].source == SkillToolSource.private
        assert res[0].version == "0.1.0"

    async def test_duplicate_deploy_raises(self, session: AsyncSession) -> None:
        await seed_builtin(session)
        await deploy_plugin(session, _manifest())
        with pytest.raises(PluginValidationError):
            await deploy_plugin(session, _manifest())

    async def test_missing_dependency_raises(self, session: AsyncSession) -> None:
        await seed_builtin(session)
        with pytest.raises(DependencyError) as exc_info:
            await deploy_plugin(
                session, _manifest(depends_on=["tool:pdf_parse@^2.0", "skill:nope@^1.0"])
            )
        assert exc_info.value.missing == ["tool:pdf_parse@^2.0", "skill:nope@^1.0"]

    async def test_uninstall_removes_plugin_and_resources(self, session: AsyncSession) -> None:
        await seed_builtin(session)
        plugin = await deploy_plugin(session, _manifest())
        await session.commit()
        await uninstall_plugin(session, plugin)
        await session.commit()
        assert await get_plugin(session, plugin.id) is None
        rows = await session.scalars(
            select(SkillTool).where(SkillTool.owner_id == plugin.name)
        )
        assert list(rows) == []
