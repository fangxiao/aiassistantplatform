"""沙箱执行器(基于 @anthropic-ai/sandbox-runtime / srt)。

阶段一实现：预埋分流架构，默认处于旁路关闭状态 (sandbox_enabled=False)。
待后续对外开放时，通过 settings.sandbox_enabled=True 一键开启。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentplatform.config import settings
from agentplatform.core.registry.model import SkillTool
from agentplatform.core.sandbox.policy import SandboxPolicy, generate_sandbox_policy

logger = logging.getLogger(__name__)

# 高危工具关键词集合
HIGH_RISK_KEYWORDS = frozenset([
    "bash", "sh", "shell", "exec", "eval", "code", "run_code",
    "python_code", "interpreter", "terminal", "cmd", "system"
])


@dataclass
class SandboxResult:
    """沙箱执行结果。"""

    success: bool
    stdout: str
    stderr: str
    returncode: int
    violation: bool = False


def is_sandbox_available(cmd: str | None = None) -> bool:
    """探测宿主环境是否已安装 srt 命令。"""
    runner_cmd = cmd or settings.sandbox_runner_cmd
    return shutil.which(runner_cmd) is not None


def is_high_risk_tool(resource: SkillTool | None) -> bool:
    """根据资源 ID、Schema 与名称判断工具是否属于高风险代码/命令执行类。"""
    if resource is None:
        return False

    rid = (resource.id or "").lower()
    rname = (resource.name or "").lower()

    # 1. 明确属于低风险内置/业务工具，直接放行 (如 PDF 解析、端侧微信真机驱动、PRD 评分)
    if any(k in rid for k in ["pdf_parse", "browser_", "wechat", "summarize", "structured_output", "score"]):
        return False

    # 2. 检查资源 ID 与名称中是否含有高危关键词
    for kw in HIGH_RISK_KEYWORDS:
        if kw in rid or kw in rname:
            return True

    # 3. 检查 Schema 属性
    raw_schema = getattr(resource, "schema_", None) or getattr(resource, "schema", None)
    schema = raw_schema if isinstance(raw_schema, dict) else {}
    props = schema.get("properties", {})
    if any(k in props for k in ["code", "script", "command", "bash"]):
        return True

    return False


async def execute_command_in_sandbox(
    cmd: list[str],
    policy: SandboxPolicy | None = None,
    cwd: Path | str | None = None,
    timeout: int | None = None,
    plugin_name: str | None = None,
) -> SandboxResult:
    """在 srt 沙箱包装下执行命令。若沙箱未开启，则直接原生执行(旁路)。"""
    timeout_sec = timeout or settings.sandbox_timeout_seconds

    # 旁路模式：沙箱未开启，直接通过 asyncio.create_subprocess_exec 执行
    if not settings.sandbox_enabled:
        logger.debug("沙箱处于旁路状态，直接执行子进程: %s", cmd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except TimeoutError:
            proc.kill()
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"命令执行超时 ({timeout_sec}s)",
                returncode=-1,
                violation=False,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return SandboxResult(
            success=(proc.returncode == 0),
            stdout=stdout,
            stderr=stderr,
            returncode=proc.returncode or 0,
            violation=False,
        )

    # 开启模式：检查 srt 是否可用
    runner_cmd = settings.sandbox_runner_cmd
    if not is_sandbox_available(runner_cmd):
        logger.warning("沙箱已开启但未检测到 '%s' 命令，降级执行并记录安全告警", runner_cmd)
        # 降级模式，避免阻断服务
        return await execute_command_in_sandbox(cmd, policy=None, cwd=cwd, timeout=timeout_sec)

    # 生成临时 settings 策略文件
    actual_policy = policy or generate_sandbox_policy(plugin_name=plugin_name)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        actual_policy.dump(Path(f.name))
        settings_file = f.name

    try:
        # 组装 srt 调用命令: srt --settings <file> -- <cmd...>
        full_cmd = [runner_cmd, "--settings", settings_file, "--", *cmd]
        logger.info("启动 srt 沙箱隔离执行: %s", full_cmd)

        proc = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except TimeoutError:
            proc.kill()
            return SandboxResult(
                success=False,
                stdout="",
                stderr=f"沙箱命令执行超时 ({timeout_sec}s)",
                returncode=-1,
                violation=False,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # 探测是否触发沙箱越权告警
        violation = False
        lower_err = stderr.lower()
        if "operation not permitted" in lower_err or "tunnel failed" in lower_err or "violation" in lower_err:
            violation = True

        return SandboxResult(
            success=(proc.returncode == 0 and not violation),
            stdout=stdout,
            stderr=stderr,
            returncode=proc.returncode or 0,
            violation=violation,
        )
    finally:
        if os.path.exists(settings_file):
            os.remove(settings_file)
