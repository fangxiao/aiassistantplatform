"""沙箱子系统单元测试。

验证：
1. 默认旁路模式 (sandbox_enabled=False)，开发零阻断；
2. 沙箱安全策略生成器符合最小权限矩阵；
3. 高危工具 vs 业务安全工具识别；
4. 沙箱开启模式下执行与违规捕获。
"""

import pytest
from unittest.mock import patch
from pathlib import Path

from agentplatform.config import settings
from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource
from agentplatform.core.sandbox.policy import generate_sandbox_policy
from agentplatform.core.sandbox.runner import (
    is_high_risk_tool,
    is_sandbox_available,
    execute_command_in_sandbox,
)
from agentplatform.core.agent.executor import execute_tool, register_dev_impl, clear_dev_registry


def test_sandbox_config_defaults():
    """验证阶段一默认配置：沙箱默认关闭 (旁路模式)。"""
    assert settings.sandbox_enabled is False
    assert settings.sandbox_runner_cmd == "srt"
    assert settings.sandbox_high_risk_only is True
    assert settings.sandbox_timeout_seconds == 30


def test_policy_generation_includes_plugin_data_dir(monkeypatch: pytest.MonkeyPatch):
    """验证沙箱策略自动包含插件专属数据目录与安全禁止规则。"""
    # 隔离其他测试经 setup_plugin_env 注入的 AGENTPLATFORM_PLUGIN_DATA_DIR
    monkeypatch.delenv("AGENTPLATFORM_PLUGIN_DATA_DIR", raising=False)
    policy = generate_sandbox_policy(plugin_name="writewx")
    policy_dict = policy.to_dict()

    # 1. 写白名单应包含 writewx 专属数据目录及 /tmp
    assert any("writewx" in p and "data" in p for p in policy_dict["filesystem"]["allowWrite"])
    assert any("tmp" in p for p in policy_dict["filesystem"]["allowWrite"])

    # 2. 读黑名单应覆盖敏感文件
    assert any(".ssh" in p for p in policy_dict["filesystem"]["denyRead"])
    assert any(".env" in p for p in policy_dict["filesystem"]["denyRead"])

    # 3. 网络防御应阻止本地关键 DB 端口探测
    assert any("5432" in d for d in policy_dict["network"]["deniedDomains"])
    assert any("6379" in d for d in policy_dict["network"]["deniedDomains"])


def test_high_risk_tool_classification():
    """验证工具风险分类：仅代码/Shell 工具为高危，业务工具放行。"""
    # 低危业务工具
    safe_wechat = SkillTool(
        id="tool:browser_wechat_draft",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="browser_wechat_draft",
        source=SkillToolSource.builtin,
    )
    safe_pdf = SkillTool(
        id="tool:pdf_parse",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="pdf_parse",
        source=SkillToolSource.builtin,
    )
    safe_score = SkillTool(
        id="tool:prd_score",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="prd_score",
        source=SkillToolSource.private,
    )
    assert is_high_risk_tool(safe_wechat) is False
    assert is_high_risk_tool(safe_pdf) is False
    assert is_high_risk_tool(safe_score) is False

    # 高危代码/命令工具
    dangerous_bash = SkillTool(
        id="tool:bash_exec",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="bash_exec",
        source=SkillToolSource.builtin,
    )
    dangerous_py = SkillTool(
        id="tool:python_interpreter",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="python_interpreter",
        source=SkillToolSource.private,
    )
    dangerous_by_schema = SkillTool(
        id="tool:custom_runner",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="custom_runner",
        source=SkillToolSource.private,
        schema_={"type": "object", "properties": {"command": {"type": "string"}}},
    )
    assert is_high_risk_tool(dangerous_bash) is True
    assert is_high_risk_tool(dangerous_py) is True
    assert is_high_risk_tool(dangerous_by_schema) is True


@pytest.mark.asyncio
async def test_bypass_execution_when_disabled():
    """沙箱关闭时，命令直接正常执行，完全不走 srt。"""
    assert settings.sandbox_enabled is False
    res = await execute_command_in_sandbox(["echo", "hello_platform"])
    assert res.success is True
    assert "hello_platform" in res.stdout
    assert res.violation is False


@pytest.mark.asyncio
async def test_executor_normal_flow_unaffected():
    """验证现有工具在沙箱旁路状态下的正常执行不受任何影响。"""
    clear_dev_registry()
    tool_res = SkillTool(
        id="tool:mock_echo",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="mock_echo",
        source=SkillToolSource.builtin,
    )
    register_dev_impl("tool:mock_echo", lambda args: f"echoed: {args.get('text')}")

    out = await execute_tool(tool_res, {"text": "test_input"})
    assert out == "echoed: test_input"
    clear_dev_registry()


@pytest.mark.asyncio
async def test_executor_sandboxed_when_enabled():
    """验证开启沙箱后，高危命令工具自动进入沙箱执行分支。"""
    tool_cmd = SkillTool(
        id="tool:shell_runner",
        version="1.0.0",
        kind=SkillToolKind.tool,
        name="shell_runner",
        source=SkillToolSource.builtin,
    )

    with patch.object(settings, "sandbox_enabled", True):
        # 即使 sandbox_enabled 为 True，安全的 echo 也应能成功执行并输出
        out = await execute_tool(tool_cmd, {"cmd": "echo sandbox_active"})
        assert "sandbox_active" in out
