"""normalize_model 测试(M18 T18.3 路由保护):auto 语义收口为平台默认模型。"""

import pytest

from agentplatform.config import settings
from agentplatform.core.llm.router import normalize_model


class TestNormalizeModel:
    def test_auto_maps_to_default(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        assert normalize_model("auto") == "glm-5.3-flash"
        assert normalize_model("AUTO") == "glm-5.3-flash"
        assert normalize_model("round_robin") == "glm-5.3-flash"
        assert normalize_model("default") == "glm-5.3-flash"
        assert normalize_model("") == "glm-5.3-flash"
        assert normalize_model(None) == "glm-5.3-flash"

    def test_explicit_model_passthrough(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        assert normalize_model("deepseek-v4-pro") == "deepseek-v4-pro"
        assert normalize_model("gpt-oss-120b") == "gpt-oss-120b"
