"""插件持久化数据目录规范与环境变量注入测试。"""

import os
from pathlib import Path

import pytest

from agentplatform.core.plugin.env import get_plugin_data_dir, setup_plugin_env
from agentplatform.core.registry.builtin import browser_wechat_draft
from agentplatform.sdk import Context, get_base_url, get_plugin_data_dir as sdk_get_plugin_data_dir


def test_plugin_data_dir_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTPLATFORM_PLUGIN_DATA_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    data_dir = get_plugin_data_dir("writewx")
    assert data_dir == tmp_path / ".agentplatform" / "plugins" / "writewx" / "data"
    assert data_dir.is_dir()


def test_plugin_data_dir_env_override(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom_data"
    custom_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTPLATFORM_PLUGIN_DATA_DIR", str(custom_dir))

    data_dir = get_plugin_data_dir("writewx")
    assert data_dir == custom_dir


def test_setup_plugin_env(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTPLATFORM_PLUGIN_DATA_DIR", raising=False)
    monkeypatch.delenv("AGENTPLATFORM_BASE_URL", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    # 创建一个模拟插件工程
    plugin_dir = tmp_path / "my_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.yaml").write_text("name: test-assistant\nversion: 0.1.0\n", encoding="utf-8")

    data_dir = setup_plugin_env(plugin_dir, target_url="http://remote-platform:9000")
    assert data_dir == tmp_path / ".agentplatform" / "plugins" / "test-assistant" / "data"
    assert data_dir.is_dir()

    assert os.environ["AGENTPLATFORM_PLUGIN_DATA_DIR"] == str(data_dir)
    assert os.environ["AGENTPLATFORM_BASE_URL"] == "http://remote-platform:9000"


def test_sdk_context_properties(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGENTPLATFORM_BASE_URL", "http://test-server:8000")
    monkeypatch.setenv("AGENTPLATFORM_PLUGIN_DATA_DIR", str(tmp_path / "my_data"))

    ctx = Context()
    assert str(ctx.data_dir) == str(tmp_path / "my_data")
    assert ctx.base_url == "http://test-server:8000"
    assert get_base_url() == "http://test-server:8000"


def test_browser_wechat_draft_metadata():
    res = browser_wechat_draft.RESOURCE
    assert res["id"] == "tool:browser_wechat_draft"
    assert "零凭据" in res["description"]
    assert "端侧真机工具" in res["description"]
    params = res["schema"]["parameters"]["properties"]
    assert "title" in params
    assert "html_content" in params
    assert "author" in params
    assert "digest" in params
    assert "theme" in params
