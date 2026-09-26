"""外链图片代理缓存(T18 优化项8,平台承接)。

动机:文章 HTML 引用的外部图片存在防盗链/失效/加载慢问题,微信编辑器
转存前预览体验差。平台提供带签名的图片代理端点(files/img,服务端抓取
+本地缓存)与 SDK 一行式改写助手(rewrite_html),插件写盘前调用即可
把 HTML 中全部外链 <img> 转为平台代理 URL。

安全:仅 http/https;解析后 IP 必须为公网(防 SSRF);响应须为图片;
大小/超时受限;代理 URL 走与 files/raw 同款 HMAC 签名(7 天有效)。
"""

import hashlib
import ipaddress
import re
import socket
from pathlib import Path

import httpx

from agentplatform.config import settings
from agentplatform.api.files import _file_sig

IMG_SIG_TTL = 7 * 24 * 3600
IMG_MAX_BYTES = 10 * 1024 * 1024
_IMG_SRC_RE = re.compile(r'(<img[^>]*?\bsrc=")(https?://[^"]+)(")', re.IGNORECASE)
_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "image/webp": ".webp", "image/svg+xml": ".svg", "image/x-icon": ".ico"}


def img_sig(url: str, exp: str) -> str:
    return _file_sig(f"img:{url}", exp)


def is_public_http_url(url: str) -> bool:
    """http/https 且解析出的 IP 全部为公网(阻断 SSRF:回环/私网/链路本地)。"""
    if not re.match(r"^https?://", url, re.IGNORECASE):
        return False
    try:
        host = httpx.URL(url).host
        if not host:
            return False
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if not ip.is_global:
                return False
        return True
    except Exception:  # noqa: BLE001  解析失败一律不放行
        return False


def img_cache_path(url: str) -> Path:
    """外链图缓存落盘路径:~/.agentplatform/imgcache/<sha256(url)>.<ext>。"""
    digest = hashlib.sha256(url.encode()).hexdigest()[:32]
    cache_dir = Path.home() / ".agentplatform" / "imgcache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(httpx.URL(url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico"}:
        suffix = ""
    return cache_dir / f"{digest}{suffix}"


def signed_img_url(url: str) -> str:
    """外链图 → 平台代理签名 URL(public_api_base 配置时为绝对地址)。"""
    import time
    from urllib.parse import urlencode

    exp = str(int(time.time()) + IMG_SIG_TTL)
    qs = urlencode({"u": url, "exp": exp, "sig": img_sig(url, exp)})
    proxy = f"/api/files/img?{qs}"
    base = (settings.public_api_base or "").rstrip("/")
    return base + proxy if base else proxy


async def fetch_and_cache(url: str) -> Path:
    """抓取外链图并落缓存;命中缓存直接返回。失败抛异常(由端点转 502)。"""
    cache = img_cache_path(url)
    if cache.exists() and cache.stat().st_size > 0:
        return cache
    if not is_public_http_url(url):
        raise ValueError("URL 不允许(需公网 http/https)")
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not ctype.startswith("image/"):
        raise ValueError(f"非图片内容: {ctype}")
    if len(resp.content) > IMG_MAX_BYTES:
        raise ValueError("图片超过 10MB 上限")
    cache = img_cache_path(url)
    if not cache.suffix:
        cache = cache.with_suffix(_EXT_BY_TYPE.get(ctype, ".png"))
    cache.write_bytes(resp.content)
    return cache


def rewrite_html(html: str) -> str:
    """把 HTML 中全部外链 <img src> 改写为平台代理签名 URL(幂等)。

    跳过:本平台自身文件(/api/files)、已是代理地址的 URL。
    """

    def _repl(m: re.Match[str]) -> str:
        url = m.group(2)
        if "/api/files/" in url or "/api/files/img" in url:
            return m.group(0)
        if not is_public_http_url(url):
            return m.group(0)  # 非公网 URL 保持原样(签名代理也不可达)
        return f'{m.group(1)}{signed_img_url(url)}{m.group(3)}'

    return _IMG_SRC_RE.sub(_repl, html)
