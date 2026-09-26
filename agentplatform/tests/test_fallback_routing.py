"""对话客户端兜底路由测试:同网关换模型也应触发 fallback(T18 事故补强)。"""

import pytest

from agentplatform.config import settings
from agentplatform.core.chat.service import make_llm_client
from agentplatform.core.llm.model import LlmEndpoint


@pytest.mark.asyncio
class TestResolveClientFallback:
    async def test_same_gateway_different_model_appends_fallback(self, session, monkeypatch) -> None:
        """主备同网关、模型不同:fallback 必须追加(单模型上游故障的容灾)。"""
        monkeypatch.setattr(settings, "openai_base_url", "https://gw.test/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        monkeypatch.setattr(settings, "fallback_openai_base_url", "https://gw.test/v1")
        monkeypatch.setattr(settings, "fallback_openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "fallback_default_model", "deepseek-v4.1-flash")

        client = await make_llm_client(session, "glm-5.3-flash", user_id=None)
        names = [ep.name for ep in client.fallback_endpoints]
        assert names == ["fallback_env"], f"同网关换模型应触发兜底,实际: {names}"

    async def test_same_gateway_same_model_no_fallback(self, session, monkeypatch) -> None:
        """主备完全相同(网关+模型):重复兜底无意义,不追加。"""
        monkeypatch.setattr(settings, "openai_base_url", "https://gw.test/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        monkeypatch.setattr(settings, "fallback_openai_base_url", "https://gw.test/v1")
        monkeypatch.setattr(settings, "fallback_openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "fallback_default_model", "glm-5.3-flash")

        client = await make_llm_client(session, None, user_id=None)
        assert client.fallback_endpoints == []

    async def test_different_gateway_appends_fallback(self, session, monkeypatch) -> None:
        """不同网关(原始设计场景):fallback 追加,行为不变。"""
        monkeypatch.setattr(settings, "openai_base_url", "https://gw.test/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "default_model", "glm-5.3-flash")
        monkeypatch.setattr(settings, "fallback_openai_base_url", "https://other.test/v1")
        monkeypatch.setattr(settings, "fallback_openai_api_key", "sk-other")
        monkeypatch.setattr(settings, "fallback_default_model", "deepseek-v4.1-flash")

        client = await make_llm_client(session, None, user_id=None)
        assert [ep.name for ep in client.fallback_endpoints] == ["fallback_env"]
