"""M16 模板准入测试(设计 013 §1):每个模板 init 后 validate 零错、test 全过。"""

from pathlib import Path

import pytest

from agentplatform.cli.main import _init_from_template
from agentplatform.cli.test_cases import run_tests
from agentplatform.cli.validate import validate_project
from agentplatform.cli_templates import TEMPLATES


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
def test_template_admission(template_id: str, tmp_path: Path, monkeypatch) -> None:
    """模板准入:生成的骨架 validate 零错误、test 全过——模板质量即生态门面。"""
    import argparse

    args = argparse.Namespace(
        name=str(tmp_path / "probe-plugin"),
        display_name="准入测试助手",
        target="http://localhost:8000",
    )
    rc = _init_from_template(args, tmp_path / "probe-plugin", template_id, "probe-plugin", "准入测试助手")
    assert rc == 0

    root = tmp_path / "probe-plugin"
    result = validate_project(root)
    assert result["ok"], result["errors"]  # validate 零错误
    assert run_tests(root) == 0  # test 全过


def test_templates_api_contract() -> None:
    """specs API 契约:清单字段齐全,文件集含 plugin.yaml 与 test。"""
    for tid, tpl in TEMPLATES.items():
        assert tpl["name"] and tpl["description"]
        assert "plugin.yaml" in tpl["files"]
        assert any(f.startswith("test/") for f in tpl["files"]), tid
        assert "{plugin_name}" in tpl["files"]["plugin.yaml"]  # 占位符待替换
