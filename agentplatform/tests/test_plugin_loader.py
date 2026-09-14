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
from agentplatform.core.registry.service import resolve, seed_builtin


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

    async def test_redeploy_same_name_overwrites_in_place(
        self, session: AsyncSession
    ) -> None:
        """ADR 0007:同名重部署原地覆盖——UUID 稳定,旧版本私有资源清除。"""
        await seed_builtin(session)
        first = await deploy_plugin(session, _manifest())
        await session.commit()

        v2 = _manifest(
            version="0.2.0",
            description="PRD 评审助手 v2",
            skills=[
                ResourceDef(
                    id="skill:prd_review_v2",
                    file="./skills/prd_review_v2.py",
                    schema={"parameters": {"type": "object"}},
                )
            ],
        )
        updated = await deploy_plugin(session, v2)
        await session.commit()

        # 同一行:UUID 保留,版本标签与清单更新
        assert updated.id == first.id
        assert updated.version == "0.2.0"
        assert updated.manifest["description"] == "PRD 评审助手 v2"

        # 旧版本私有资源已清除,只余本次清单的资源
        rows = await session.scalars(
            select(SkillTool).where(SkillTool.owner_id == first.name)
        )
        res = list(rows)
        assert {r.id for r in res} == {"skill:prd_review_v2"}
        assert all(r.version == "0.2.0" for r in res)

        # 历史会话按原 plugin_id 仍能取到插件(不悬挂,自动获得新版本)
        assert (await get_plugin(session, first.id)) is updated

    async def test_missing_dependency_raises(self, session: AsyncSession) -> None:
        await seed_builtin(session)
        with pytest.raises(DependencyError) as exc_info:
            await deploy_plugin(
                session, _manifest(depends_on=["tool:pdf_parse@^2.0", "skill:nope@^1.0"])
            )
        assert exc_info.value.missing == ["tool:pdf_parse@^2.0", "skill:nope@^1.0"]

    async def test_optional_dependency_falls_back_to_local(
        self, session: AsyncSession
    ) -> None:
        """T11.10:可选依赖平台缺失不阻断部署,运行时回退插件本地同名实现。"""
        await seed_builtin(session)
        manifest = _manifest(
            depends_on=["tool:fallback_demo@^1.0?"],
            tools=[
                ResourceDef(
                    id="tool:fallback_demo",
                    file="./tools/fallback_demo.py",
                    schema={"parameters": {"type": "object"}},
                )
            ],
        )
        plugin = await deploy_plugin(session, manifest)
        await session.commit()
        assert plugin.name == "prd-review-assistant"

        # 平台无公共版,resolve(与 build_tools 一致不带版本约束)回退到私有实现
        resolved = await resolve(session, "tool:fallback_demo")
        assert resolved is not None
        assert resolved.source == SkillToolSource.private
        assert resolved.owner_id == "prd-review-assistant"

    async def test_local_resource_colliding_public_id_version_rejected(
        self, session: AsyncSession
    ) -> None:
        """T11.10:本地回退实现与平台公共资源同 id+version 会覆盖公共行,必须拒绝。"""
        await seed_builtin(session)
        manifest = _manifest(
            name="greedy-plugin",
            version="1.0.0",  # 与 tool:pdf_parse 公共版本撞键
            depends_on=[],
            tools=[
                ResourceDef(
                    id="tool:pdf_parse",
                    file="./tools/pdf_parse.py",
                    schema={"parameters": {"type": "object"}},
                )
            ],
        )
        with pytest.raises(PluginValidationError, match="撞 id\\+version"):
            await deploy_plugin(session, manifest)

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
