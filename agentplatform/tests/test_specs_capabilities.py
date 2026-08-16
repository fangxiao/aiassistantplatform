"""平台共享能力、22 种控件元数据与 CLI 增强功能测试。"""

from pathlib import Path
from unittest.mock import patch

from httpx import AsyncClient

from agentplatform.cli.main import (
    cmd_guide,
    cmd_init,
    cmd_registry,
    cmd_update,
    cmd_widgets,
    main,
)
from agentplatform.core.registry.capabilities import (
    CONTENT_BLOCKS_CATALOG,
    get_capabilities_manifest,
)


class TestCapabilitiesCatalog:
    def test_catalog_structure(self) -> None:
        manifest = get_capabilities_manifest()
        assert manifest["platform"] == "AgentPlatform"
        assert len(manifest["builtin_skills"]) == 2
        assert len(manifest["builtin_tools"]) == 1
        assert len(manifest["content_blocks"]) == 22
        assert len(CONTENT_BLOCKS_CATALOG) == 22

    def test_22_content_blocks_complete(self) -> None:
        categories = {b["category"] for b in CONTENT_BLOCKS_CATALOG}
        assert categories == {"display", "interactive", "action"}

        display_blocks = [b for b in CONTENT_BLOCKS_CATALOG if b["category"] == "display"]
        interactive_blocks = [b for b in CONTENT_BLOCKS_CATALOG if b["category"] == "interactive"]
        action_blocks = [b for b in CONTENT_BLOCKS_CATALOG if b["category"] == "action"]

        assert len(display_blocks) == 8
        assert len(interactive_blocks) == 11
        assert len(action_blocks) == 3

        for b in CONTENT_BLOCKS_CATALOG:
            assert "type" in b
            assert "name" in b
            assert "description" in b
            assert "sample_data" in b
            assert "python_snippet" in b


class TestSpecsApi:
    async def test_get_capabilities_api(self, client: AsyncClient) -> None:
        resp = await client.get("/api/specs/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert data["platform"] == "AgentPlatform"
        assert len(data["builtin_skills"]) >= 2
        assert len(data["builtin_tools"]) >= 1
        assert len(data["content_blocks"]) == 22

    async def test_get_agents_md_api(self, client: AsyncClient) -> None:
        resp = await client.get("/api/specs/agents-md")
        assert resp.status_code == 200
        data = resp.json()
        assert "template_agents_md" in data
        assert "AgentPlatform" in data["template_agents_md"]
        assert "depends_on" in data["template_agents_md"]
        assert "22 种富交互组件" in data["template_agents_md"]


class TestCliCommands:
    def test_cli_registry_command(self, capsys) -> None:
        ret = main(["registry"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "AgentPlatform 平台共享能力注册表" in captured.out
        assert "tool:pdf_parse" in captured.out
        assert "skill:summarize" in captured.out

    def test_cli_registry_json(self, capsys) -> None:
        ret = main(["registry", "--json"])
        assert ret == 0
        captured = capsys.readouterr()
        assert '"platform": "AgentPlatform"' in captured.out

    def test_cli_widgets_command(self, capsys) -> None:
        ret = main(["widgets"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "22 种富交互组件画廊" in captured.out
        assert "markdown" in captured.out
        assert "input.confirm" in captured.out
        assert "action.copy" in captured.out

    def test_cli_guide_command(self, capsys) -> None:
        ret = main(["guide"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "智能体插件开发指南" in captured.out

    def test_cli_init_and_update(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "sample_plugin"

        # 1. Test init
        ret = main(["init", str(plugin_dir)])
        assert ret == 0
        assert (plugin_dir / "plugin.yaml").exists()
        assert (plugin_dir / "skills" / "demo.py").exists()
        assert (plugin_dir / "tools" / "demo.py").exists()
        assert (plugin_dir / "test" / "test_cases.yaml").exists()
        assert (plugin_dir / "AGENTS.md").exists()
        assert (plugin_dir / "CLAUDE.md").exists()
        assert (plugin_dir / ".cursorrules").exists()
        assert (plugin_dir / ".agents" / "skills" / "agentplatform-plugin-dev" / "SKILL.md").exists()

        # Validate that init generated valid files
        ret_val = main(["validate", str(plugin_dir)])
        assert ret_val == 0

        # 2. Test update
        ret_up = main(["update", str(plugin_dir)])
        assert ret_up == 0
        assert (plugin_dir / "AGENTS.md").exists()
