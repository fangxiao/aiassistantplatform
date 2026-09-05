"""沙箱策略生成器(基于 @anthropic-ai/sandbox-runtime / srt 契约规范)。

负责为插件/高危工具动态生成细粒度沙箱安全策略(JSON):
- 允许写: 插件专属数据目录 (~/.agentplatform/plugins/<name>/data/) 与系统临时目录 (/tmp)
- 严禁读: ~/.ssh, ~/.aws, ~/.gnupg, .env 凭据
- 严禁写: 系统关键配置文件与 hook 脚本
- 网络防御: 放行常规外网域名与平台服务端口，阻止内部核心数据库端口(5432/6379)探测
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentplatform.core.plugin.env import get_plugin_data_dir


@dataclass
class SandboxPolicy:
    """srt 沙箱策略模型。"""

    allow_read: list[str] = field(default_factory=list)
    deny_read: list[str] = field(default_factory=lambda: [
        str(Path.home() / ".ssh"),
        str(Path.home() / ".aws"),
        str(Path.home() / ".gnupg"),
        "**/.env",
        "**/.env.*",
    ])
    allow_write: list[str] = field(default_factory=list)
    deny_write: list[str] = field(default_factory=lambda: [
        "**/.bashrc",
        "**/.zshrc",
        "**/.profile",
        "**/.git/hooks/**",
    ])
    allowed_domains: list[str] = field(default_factory=lambda: [
        "localhost",
        "127.0.0.1",
        "*.anthropic.com",
        "*.openai.com",
        "api.ailearning.top",
        "*.weixin.qq.com",
    ])
    denied_domains: list[str] = field(default_factory=lambda: [
        "127.0.0.1:5432",
        "localhost:5432",
        "127.0.0.1:6379",
        "localhost:6379",
        "169.254.169.254",  # 云厂商元数据服务
    ])

    def to_dict(self) -> dict[str, Any]:
        """输出符合 srt settings 格式的配置字典。"""
        return {
            "network": {
                "allowedDomains": self.allowed_domains,
                "deniedDomains": self.denied_domains,
                "allowLocalBinding": True,
            },
            "filesystem": {
                "allowRead": self.allow_read,
                "denyRead": self.deny_read,
                "allowWrite": self.allow_write,
                "denyWrite": self.deny_write,
            },
        }

    def dump(self, path: Path) -> None:
        """持久化策略文件至指定路径。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def generate_sandbox_policy(
    plugin_name: str | None = None,
    extra_write_paths: list[str] | None = None,
    extra_allowed_domains: list[str] | None = None,
) -> SandboxPolicy:
    """根据插件上下文动态生成默认最小权限沙箱策略。"""
    policy = SandboxPolicy()

    # 1. 挂载写白名单
    write_paths = [tempfile.gettempdir(), "/tmp"]
    if plugin_name:
        data_dir = get_plugin_data_dir(plugin_name)
        write_paths.append(str(data_dir.resolve()))
    if extra_write_paths:
        write_paths.extend(extra_write_paths)
    policy.allow_write = list(dict.fromkeys(write_paths))

    # 2. 补充域名白名单
    if extra_allowed_domains:
        policy.allowed_domains = list(dict.fromkeys(policy.allowed_domains + extra_allowed_domains))

    return policy
