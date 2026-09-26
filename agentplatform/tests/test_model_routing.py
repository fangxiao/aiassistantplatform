"""normalize_model 测试:auto 透传网关(2026-09-26 用户裁决修订),空值回平台默认。"""

import pytest

from agentplatform.config import settings
from agentplatform.core.llm.router import normalize_model


class TestNormalizeModel:
    def test_empty_maps_to_default(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        assert normalize_model("") == "glm-5.3-flash"
        assert normalize_model(None) == "glm-5.3-flash"

    def test_auto_passthrough(self, monkeypatch) -> None:
        """auto 原样透传:路由智能归网关,弱模型排除走网关侧 auto 池黑名单。"""
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        assert normalize_model("auto") == "auto"
        assert normalize_model("round_robin") == "round_robin"

    def test_explicit_model_passthrough(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        assert normalize_model("deepseek-v4-pro") == "deepseek-v4-pro"
