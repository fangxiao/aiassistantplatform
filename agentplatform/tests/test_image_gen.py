"""tool:image_gen 测试(M18):参数校验/生图落盘回 URL/未配置降级/registry 登记。"""

import base64
import json

import httpx

from agentplatform.config import settings
from agentplatform.core.agent.image_gen import IMAGE_GEN_TOOL_ID, RESOURCE
from agentplatform.core.agent.image_gen import run as run_image_gen

# 1x1 透明 PNG 的 b64(足够小,断言只看落盘与非空)
_PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcffff3f030005fe02fea72d3e290000000049454e44ae426082"
    )
).decode()


def _mock_client(payload: dict, status: int = 200):
    """按 web_search 测试同款 MockTransport 模式构造假网关。"""
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["prompt"]
        return httpx.Response(status, json=payload)

    class _Client(real_client):
        def __init__(self, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(**kw)

    return _Client


class TestImageGenTool:
    async def test_empty_prompt_rejected(self) -> None:
        out = json.loads(await run_image_gen({"prompt": "  "}))
        assert out["ok"] is False

    async def test_missing_config_degrades(self, monkeypatch) -> None:
        """网关凭据全空时优雅降级,回填可自纠提示而非崩溃。"""
        monkeypatch.setattr(settings, "image_gen_base_url", "")
        monkeypatch.setattr(settings, "image_gen_api_key", "")
        monkeypatch.setattr(settings, "openai_base_url", "")
        monkeypatch.setattr(settings, "openai_api_key", "")
        out = json.loads(await run_image_gen({"prompt": "一只猫"}))
        assert out["ok"] is False
        assert "OPENAI_BASE_URL" in out["error"]

    async def test_b64_landed_and_url_returned(self, monkeypatch, tmp_path) -> None:
        """b64 产物落盘 uploads,回填 /api/files/raw 白名单 URL。"""
        monkeypatch.setattr(settings, "image_gen_base_url", "http://gw.test/v1")
        monkeypatch.setattr(settings, "image_gen_api_key", "sk-test")
        monkeypatch.setattr("agentplatform.core.agent.image_gen._uploads_dir", lambda: tmp_path)

        real = httpx.AsyncClient
        httpx.AsyncClient = _mock_client({"data": [{"b64_json": _PNG_1PX}]})
        try:
            out = json.loads(await run_image_gen({"prompt": "赛博朋克城市夜景", "size": "1024x1024"}))
        finally:
            httpx.AsyncClient = real
        assert out["ok"] is True
        assert len(out["images"]) == 1
        assert out["images"][0]["url"].startswith("/api/files/raw?path=")
        landed = list(tmp_path.glob("*.png"))
        assert len(landed) == 1 and landed[0].read_bytes()[:4] == b"\x89PNG"

    async def test_url_response_passthrough(self, monkeypatch) -> None:
        """网关直接回 url 形态时透传,不落盘。"""
        monkeypatch.setattr(settings, "image_gen_base_url", "http://gw.test/v1")
        monkeypatch.setattr(settings, "image_gen_api_key", "sk-test")

        real = httpx.AsyncClient
        httpx.AsyncClient = _mock_client({"data": [{"url": "https://cdn.example.com/a.png"}]})
        try:
            out = json.loads(await run_image_gen({"prompt": "logo"}))
        finally:
            httpx.AsyncClient = real
        assert out["ok"] is True
        assert out["images"][0]["url"] == "https://cdn.example.com/a.png"

    async def test_http_error_degrades(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "image_gen_base_url", "http://gw.test/v1")
        monkeypatch.setattr(settings, "image_gen_api_key", "sk-test")

        real = httpx.AsyncClient
        httpx.AsyncClient = _mock_client({"error": "rate limited"}, status=429)
        try:
            out = json.loads(await run_image_gen({"prompt": "x"}))
        finally:
            httpx.AsyncClient = real
        assert out["ok"] is False
        assert "生图请求失败" in out["error"]

    async def test_empty_data_degrades(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "image_gen_base_url", "http://gw.test/v1")
        monkeypatch.setattr(settings, "image_gen_api_key", "sk-test")

        real = httpx.AsyncClient
        httpx.AsyncClient = _mock_client({"created": 1, "data": []})
        try:
            out = json.loads(await run_image_gen({"prompt": "x"}))
        finally:
            httpx.AsyncClient = real
        assert out["ok"] is False
        assert "未返回可用图片" in out["error"]


class TestRegistryRegistration:
    def test_resource_in_builtin_all(self) -> None:
        from agentplatform.core.registry.builtin import ALL

        assert any(r["id"] == IMAGE_GEN_TOOL_ID for r in ALL)
        assert RESOURCE["kind"] == "tool"
        assert RESOURCE["schema"]["parameters"]["required"] == ["prompt"]
