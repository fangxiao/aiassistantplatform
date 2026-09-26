"""图片代理缓存测试(T18 项8):SSRF 防护/改写幂等/签名 URL/抓取校验。

不依赖真实外网:DNS 解析与网络传输均 mock。
"""

import base64

import httpx
import pytest

from agentplatform.config import settings
from agentplatform.core.agent import img_proxy as ip
from agentplatform.core.agent.img_proxy import (
    fetch_and_cache,
    is_public_http_url,
    rewrite_html,
    signed_img_url,
)

_REAL_ASYNC_CLIENT = httpx.AsyncClient  # mock 前的真实类(防子类化叠加)

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _mock_dns(monkeypatch, ip_answer: str = "93.184.216.34") -> None:
    """让所有域名解析到指定 IP(默认公网)。"""
    monkeypatch.setattr(
        ip.socket, "getaddrinfo",
        lambda host, port, *a, **kw: [(2, 1, 6, "", (ip_answer, 0))],
    )


def _mock_transport(monkeypatch, payload: bytes, ctype: str = "image/png") -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": ctype})

    class _Client(_REAL_ASYNC_CLIENT):
        def __init__(self, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(**kw)

    monkeypatch.setattr(ip.httpx, "AsyncClient", _Client)


class TestSsrfGuard:
    def test_private_blocked(self, monkeypatch) -> None:
        _mock_dns(monkeypatch, "127.0.0.1")
        assert not is_public_http_url("http://example.com/x.png")
        _mock_dns(monkeypatch, "192.168.1.1")
        assert not is_public_http_url("http://example.com/a.png")
        _mock_dns(monkeypatch, "10.0.0.1")
        assert not is_public_http_url("http://example.com/a.png")

    def test_scheme_blocked(self) -> None:
        assert not is_public_http_url("file:///etc/passwd")
        assert not is_public_http_url("ftp://example.com/a.png")

    def test_public_allowed(self, monkeypatch) -> None:
        _mock_dns(monkeypatch, "93.184.216.34")
        assert is_public_http_url("https://cdn.example.com/a.png")

    def test_dns_failure_blocked(self, monkeypatch) -> None:
        def _fail(host, port, *a, **kw):
            raise OSError("dns down")

        monkeypatch.setattr(ip.socket, "getaddrinfo", _fail)
        assert not is_public_http_url("https://cdn.example.com/a.png")


class TestRewriteHtml:
    def test_external_img_rewritten(self, monkeypatch) -> None:
        _mock_dns(monkeypatch)
        html = '<p>正文</p><img src="https://cdn.example.com/a.png" alt="x">'
        out = rewrite_html(html)
        assert out.count("/api/files/img?u=") == 1
        assert 'src="https://cdn.example.com' not in out  # src 已不再是原始外链
        assert 'alt="x"' in out

    def test_platform_files_kept(self, monkeypatch) -> None:
        _mock_dns(monkeypatch)
        html = '<img src="/api/files/raw?path=/x.png"><img src="http://localhost:8000/api/files/raw?path=/y.png">'
        assert rewrite_html(html) == html  # 平台自身文件 URL 不动

    def test_idempotent(self, monkeypatch) -> None:
        _mock_dns(monkeypatch)
        html = '<img src="https://cdn.example.com/a.png">'
        once = rewrite_html(html)
        assert rewrite_html(once) == once

    def test_private_src_untouched(self, monkeypatch) -> None:
        _mock_dns(monkeypatch, "192.168.1.5")
        html = '<img src="http://private.local/a.png">'
        assert rewrite_html(html) == html

    def test_absolute_with_public_base(self, monkeypatch) -> None:
        _mock_dns(monkeypatch)
        monkeypatch.setattr(settings, "public_api_base", "http://localhost:8000")
        url = signed_img_url("https://cdn.example.com/a.png")
        assert url.startswith("http://localhost:8000/api/files/img?")


class TestFetchAndCache:
    async def test_caches_and_serves_bytes(self, monkeypatch, tmp_path) -> None:
        _mock_dns(monkeypatch)
        _mock_transport(monkeypatch, _PNG_1PX)
        monkeypatch.setattr(ip.Path, "home", staticmethod(lambda: tmp_path))
        cache = await fetch_and_cache("https://cdn.example.com/pic.png")
        assert cache.exists() and cache.read_bytes() == _PNG_1PX
        # 二次调用命中缓存(传输层再被调用会失败,缓存命中则不会)
        again = await fetch_and_cache("https://cdn.example.com/pic.png")
        assert again == cache

    async def test_rejects_non_image(self, monkeypatch, tmp_path) -> None:
        _mock_dns(monkeypatch)
        _mock_transport(monkeypatch, b"<html>not an image</html>", "text/html")
        monkeypatch.setattr(ip.Path, "home", staticmethod(lambda: tmp_path))
        with pytest.raises(ValueError, match="非图片"):
            await fetch_and_cache("https://cdn.example.com/page.html")

    async def test_rejects_oversize(self, monkeypatch, tmp_path) -> None:
        _mock_dns(monkeypatch)
        _mock_transport(monkeypatch, b"x" * (10 * 1024 * 1024 + 1))
        monkeypatch.setattr(ip.Path, "home", staticmethod(lambda: tmp_path))
        with pytest.raises(ValueError, match="10MB"):
            await fetch_and_cache("https://cdn.example.com/big.png")
