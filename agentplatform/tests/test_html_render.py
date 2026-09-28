"""tool:html_render 测试(T18.17):参数校验/sidecar 调用/产物落盘签名/降级。"""

import base64
import json

import httpx
import pytest

from agentplatform.config import settings
from agentplatform.core.agent.html_render import HTML_RENDER_TOOL_ID, RESOURCE, run as run_html_render

_PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcffff3f030005fe02fea72d3e290000000049454e44ae426082"
    )
).decode()


def _mock_sidecar(files: dict, pages: int = 3, status: int = 200):
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["html"]
        return httpx.Response(status, json={"files": files, "pages": pages})

    class _Client(real):
        def __init__(self, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(**kw)

    return _Client


class TestHtmlRenderTool:
    async def test_empty_html_rejected(self) -> None:
        out = json.loads(await run_html_render({"html": "  "}))
        assert out["ok"] is False

    async def test_renders_and_signs(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(settings, "public_api_base", "http://localhost:8000")
        monkeypatch.setattr("agentplatform.core.agent.html_render._uploads_dir", lambda: tmp_path)
        real = httpx.AsyncClient
        httpx.AsyncClient = _mock_sidecar({"pdf": _PNG_1PX, "png": [_PNG_1PX, _PNG_1PX], "pptx": _PNG_1PX})
        try:
            out = json.loads(await run_html_render({"html": "<html><body data-pages='2'>x</body></html>"}))
        finally:
            httpx.AsyncClient = real
        assert out["ok"] is True and out["pages"] == 3
        assert out["pdf_url"].startswith("http://localhost:8000/api/files/raw?")
        assert len(out["png_urls"]) == 2
        assert out["pptx_url"]
        exts = {p.suffix for p in tmp_path.iterdir()}
        assert {".pdf", ".png", ".pptx"} <= exts

    async def test_sidecar_unreachable_degrades(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "render_service_url", "http://render.invalid:8001")
        out = json.loads(await run_html_render({"html": "<html>x</html>"}))
        assert out["ok"] is False and "渲染服务不可用" in out["error"]

    def test_registered(self) -> None:
        from agentplatform.core.registry.builtin import ALL

        assert any(r["id"] == HTML_RENDER_TOOL_ID for r in ALL)
        assert RESOURCE["schema"]["parameters"]["required"] == ["html"]
